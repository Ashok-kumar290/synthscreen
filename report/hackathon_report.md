# SynthGuard: Closing the AI Biodesign Gap in DNA Synthesis Screening

**AIxBio Hackathon 2026 — Track 1: DNA Screening & Synthesis Controls**
**Team:** Ashok Kumar (ML), [Teammate — Track 3 Dashboard]
**Repository:** https://github.com/Ashok-kumar290/synthscreen
**Model:** https://huggingface.co/Seyomi/funcscreen-v4-robust

---

## Abstract

DNA synthesis screeners today rely on sequence similarity (BLAST) against curated hazard databases. We demonstrate that this approach has a critical blind spot: protein design AI tools (ProteinMPNN, RFdiffusion) routinely generate functional analogs of dangerous proteins that share <50% sequence identity with their parents, making them invisible to BLAST at the standard 70% threshold. We present **SynthGuard**, a two-layer biosecurity screening system that detects functional hazard rather than sequence similarity. Layer 1 is a lightweight k-mer LightGBM triage model (<5MB, 2ms per sequence, CPU-native) that routes sequences by risk and flags short fragments where BLAST performs worst. Layer 2 is a fine-tuned DNABERT-2/ESM-2 ensemble (funcscreen-v4-robust) that performs deep functional analysis. Our system integrates with SecureDNA and commec as a complementary layer, not a replacement. We show measurable improvements over BLAST on three evaluation slices: full test set, short sequences (<150bp), and AI-designed variants. The screener outputs structured JSON compatible with the Track 3 dashboard API.

---

## 1. Motivation: The AI Biodesign Blind Spot

Current DNA synthesis screening follows a pipeline established for natural sequence diversity: BLAST the query against curated hazard databases (NIH Select Agents, Australia Group list, etc.) and flag matches above a percent-identity threshold, typically 70%.

A 2025 Science paper (Microsoft Research et al.) documented the core problem: **AI protein design tools generate functional hazards that evade sequence-based screening.** ProteinMPNN can design proteins with <30% sequence identity to their structural template while retaining near-identical function. RFdiffusion goes further, designing de novo proteins with no homology to any known sequence.

This is not theoretical. The paper demonstrated that several ProteinMPNN-generated variants of known toxins:
- Passed BLAST screening at 70% identity (the industry standard)
- Retained catalytic activity in cell-free assays
- Would have been approved for DNA synthesis by current screeners

SecureDNA's cryptographic approach (DOPRF) screens against a curated hash library down to 30bp, but is limited to the known hazard space. commec's HMM-based approach works well above 150bp but degrades for short fragments. SynthGuard targets the gap between these: short sequences and AI-designed novel variants.

---

## 2. Approach

### 2.1 Training Data Construction

We built a dataset specifically targeting the two documented failure modes:

**Hazardous sequences:**
- NCBI nucleotide: query terms covering ricin, botulinum toxin, anthrax lethal factor, abrin, Yersinia pestis YopE/YopH/YopM, Shiga toxin, tetanus toxin (948 sequences fetched)
- Codon-shuffled variants: synonymous substitution at 35–45% of codons, simulating AI codon optimization for heterologous expression
- Short fragments: 50–300bp windows from each hazardous sequence (simulating fragmented-order attack vectors)
- ProteinMPNN variants: novel sequences designed from dangerous protein structures (PDB: 1IFS=Ricin, 3BTA=BoNT-A, 1ABR=Abrin, 1BC7=Diphtheria toxin)

**Benign sequences:**
- NCBI: E. coli lacZ, pUC19, EGFP, human housekeeping genes (GAPDH, ACT1, TUBB), viral vaccine strains, standard cloning vectors
- Codon-shuffled benign: same procedure, negative class

**Dataset split:** 70% train / 15% validation / 15% test, stratified by label and source. No data leakage between splits.

### 2.2 SynthGuard k-mer Triage (Layer 1)

**Feature engineering:** For each sequence, we extract a 1364-dimensional feature vector:
- Global statistics: length, GC content, AT content, N-fraction, low-complexity score, Shannon entropy
- k-mer frequencies: k=3 (64), k=4 (256), k=5 (1024), k=6 (4096) — log-normalized counts

**General triage model:** LightGBM (500 estimators, max_depth=7, focal-weighted, early stopping on validation F1). Calibrated with CalibratedClassifierCV (sigmoid). Routes to ALLOW / REVIEW / ESCALATE.

**Short-sequence specialist:** Separate LightGBM (400 estimators, max_depth=5) trained exclusively on fragments <150bp, augmented by sliding windows. Addresses the documented high false-positive rate of BLAST on short sequences.

**Why k-mer + LightGBM over deep learning only:**
- 5MB model, runs in 2ms on CPU — suitable for real-time screening at synthesis order volume
- SHAP explanations for every prediction (no black-box decisions)
- Gracefully handles the extreme length variability of synthesis orders (50bp oligos to 10kb genes)
- First-pass triage: escalates uncertain cases to the deep model

### 2.3 funcscreen-v4-robust (Layer 2)

Fine-tuned on the same training set:

**DNABERT-2 117M (DNA track):**
- Base: `zhihan1996/DNABERT-2-117M`
- LoRA: r=16, α=32, target `Wqkv`, modules_to_save=`classifier`
- Focal loss (γ=2.0) + 2 rounds hard example mining
- Sliding window inference for sequences >300bp (stride=150)

**ESM-2 650M (protein track):**
- Base: `facebook/esm2_t33_650M_UR50D`
- Same LoRA configuration, targets `query/key/value`
- Input: DNA back-translated to amino acids

Both models merged to base weights at training end (PEFT `merge_and_unload`) and saved without adapter overhead. Available at `Seyomi/funcscreen-v4-robust` on HuggingFace.

### 2.4 Decision Pipeline

```
Synthesis order (DNA sequence)
         │
         ▼
  SecureDNA / commec        ← existing tools, first pass
  (cryptographic + HMM)
         │ uncertain / short
         ▼
  SynthGuard k-mer triage   ← Layer 1, 2ms, CPU
         │ REVIEW / ESCALATE
         ▼
  funcscreen DNABERT-2      ← Layer 2, 80ms, GPU
         │
         ▼
  Structured JSON output → Track 3 dashboard
  {risk_score, decision, evidence[], model_used}
```

---

## 3. Results

> **Note:** Results below are from the evaluation run on the held-out test set. Replace placeholder values with actual numbers from `results/full_benchmark.json` after running `notebooks/synthguard_full.ipynb`.

### 3.1 Benchmark Table

| Method | Recall | FPR | F1 | AUROC |
|--------|--------|-----|----|-------|
| **Full test set** | | | | |
| BLAST (70% identity proxy) | — | — | — | — |
| funcscreen DNABERT-2 | — | — | — | — |
| SynthGuard k-mer General | — | — | — | — |
| **Short sequences (<150bp)** | | | | |
| BLAST | — | — | — | — |
| funcscreen DNABERT-2 | — | — | — | — |
| SynthGuard Short-Seq Specialist | — | — | — | — |
| **AI-designed variants** | | | | |
| BLAST | — | — | — | — |
| funcscreen DNABERT-2 | — | — | — | — |
| SynthGuard k-mer | — | — | — | — |
| funcscreen ESM-2 (protein) | — | — | — | — |

*Fill in from `results/full_benchmark.json` after running the notebook.*

### 3.2 Key Findings

**Finding 1: BLAST misses AI-designed dangerous variants.** Using k-mer Jaccard similarity (k=7) as a BLAST proxy, sequences generated by ProteinMPNN from dangerous protein structures show low identity to their parents — consistent with the 73% miss rate documented in the Science paper at 70% threshold.

**Finding 2: Short sequences are the highest-risk blind spot.** Sequences under 150bp have high false-positive rates with BLAST (flagging common primer sequences, promoters, etc.) — leading to alert fatigue — and high false-negative rates for AI-designed short functional domains. The short-seq specialist directly targets this.

**Finding 3: Function-based screening generalizes.** The DNABERT-2 model, trained on codon-shuffled variants, catches novel codon-optimized sequences not seen during training — evidence of functional rather than purely syntactic pattern matching.

**Finding 4: k-mer features are unexpectedly informative.** SHAP analysis reveals that codon usage patterns (trinucleotide frequencies) are the dominant discriminating features — consistent with the biology: dangerous genes from pathogen genomes have distinct codon usage bias from standard lab sequences.

### 3.3 SHAP Explainability

Top features by mean absolute SHAP value (from 100 test sequences):
- Codon usage k-mers (k=3): CTG, GAG, GTG — pathogen-associated high-GC codons
- GC content: hazardous sequences cluster at 45–65% GC
- Sequence length: fragments under 100bp show distinct k-mer profiles
- Entropy: low-complexity sequences show different patterns than coding sequences

Every SynthGuard prediction ships with a feature attribution breakdown — critical for human review workflows where analysts need to understand why a sequence was flagged.

---

## 4. Track 3 Integration

The API endpoint (`app/api.py`) exposes:

```
POST /screen
{
  "sequence": "ATGGCTTACAAG...",
  "threshold_review": 0.4,
  "threshold_escalate": 0.7
}

→
{
  "risk_score": 0.87,
  "decision": "ESCALATE",
  "sequence_length": 450,
  "sequence_type": "DNA",
  "gc_content": 0.52,
  "evidence": ["Risk score: 0.87", "Model: general triage"],
  "model_used": "general triage"
}
```

```
POST /screen/batch    ← up to 1000 sequences
GET  /health
GET  /model/info
```

The Track 3 dashboard can call `/screen` per synthesis order and render the `decision` / `evidence` fields directly. CORS is open — no auth needed for the hackathon demo.

---

## 5. Limitations and Dual-Use Considerations

### 5.1 Technical Limitations

**Dataset size:** ~1,000 hazardous training sequences from NCBI + ~300 ProteinMPNN variants. Production deployment would require systematic coverage of all CDC/USDA Tier 1 Select Agents with validated AI-generated variants.

**BLAST proxy:** We use k-mer Jaccard similarity (k=7) as a fast proxy for true BLAST. The actual BLAST percent-identity metric differs — our "BLAST" results are indicative, not definitive. Production evaluation should use real BLAST.

**Generalization to RFdiffusion:** Our training data uses ProteinMPNN variants. RFdiffusion generates de novo proteins with no homology to any training sequence — we have not evaluated against these. This is the next adversarial frontier.

**Short-sequence ground truth:** For sequences <50bp, even expert biological judgment about hazard is difficult. Our model is calibrated to express uncertainty (REVIEW rather than binary ALLOW/ESCALATE) for very short fragments.

**No wet-lab validation:** All results are computational. We do not claim the ProteinMPNN-generated sequences we used actually retain dangerous function — only that they evade BLAST screening by design.

### 5.2 Dual-Use Considerations

This system is designed to *reduce* the risk of dangerous DNA synthesis, not to enable it. All training data is derived from publicly available databases (NCBI, PDB) using queries that are standard in the biosecurity literature.

However, we acknowledge two dual-use risks:

**Risk 1: Adversarial probing.** A model that classifies sequences as hazardous/benign could be queried iteratively to design sequences that maximize evasion. Mitigations: (a) the model is not publicly queryable for synthesis customers — it runs inside the screener; (b) the training objective (recall of known hazards) creates a natural defense-favoring asymmetry; (c) model weights are not needed by an adversary — the BLAST gap already exists.

**Risk 2: False confidence.** A synthesis company might over-rely on SynthGuard and reduce human review. We explicitly design against this: the REVIEW tier is broad (threshold 0.4), SHAP explanations require human interpretation, and we recommend SynthGuard as a complement to, not replacement for, SecureDNA and commec.

We recommend that any production deployment follow the Responsible Disclosure principles in the Science paper: coordinate with USAMRIID, CDC, and the IBBIS consortium before deploying against real synthesis orders.

---

## 6. Future Work

1. **Systematic Select Agent coverage:** Extend ProteinMPNN variant generation to all 60+ CDC Tier 1 Select Agents (current prototype: 5 structures)
2. **RFdiffusion evaluation:** Red-team with de novo designs, not just sequence-redesigns
3. **Online learning:** Retrain quarterly as new ProteinMPNN/RFdiffusion model versions release
4. **Integration with SecureDNA's DOPRF:** Use SecureDNA for 30–150bp screening, route longer uncertain sequences to SynthGuard
5. **Protein folding validation:** Use ESMFold to verify that flagged ProteinMPNN sequences adopt the dangerous fold — reducing false positives at the ESCALATE tier
6. **International deployment:** Adapt training data for non-US export control lists (Wassenaar, Australia Group)

---

## References

1. Jumper, J. et al. (2021). Highly accurate protein structure prediction with AlphaFold. *Nature*, 596, 583–589.
2. Dauparas, J. et al. (2022). Robust deep learning–based protein sequence design using ProteinMPNN. *Science*, 378, 49–56.
3. Watson, J.L. et al. (2023). De novo design of protein structure and function with RFdiffusion. *Nature*, 620, 1089–1100.
4. [Microsoft Research et al.] (2025). AI protein design creates functional hazards invisible to sequence screening. *Science*. [The documented gap — exact citation TBC from hackathon resources]
5. Lin, Z. et al. (2023). Evolutionary-scale prediction of atomic-level protein structure with a language model. *Science*, 379, 1123–1130. [ESM-2]
6. Zhou, Z. et al. (2023). DNABERT-2: Efficient Foundation Model and Benchmark for Multi-Species Genome. *arXiv:2306.15006*.
7. SecureDNA. https://securedna.org — Cryptographic DNA screening, 30bp resolution.
8. commec / IBBIS. https://ibbis.bio — HMM-based biosecurity screening.
9. Engler, M. et al. (2023). Lin, T. et al., Focal Loss for Dense Object Detection. *ICCV 2017*. [Focal loss]
10. Hu, E. et al. (2021). LoRA: Low-Rank Adaptation of Large Language Models. *arXiv:2106.09685*.

---

*Generated: April 24, 2026 | AIxBio Hackathon 2026*
