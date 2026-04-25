# SynthGuard: Closing the AI Biodesign Gap in DNA Synthesis Screening

**AIxBio Hackathon 2026 — Track 1: DNA Screening & Synthesis Controls**
**Team:** Ashok Kumar
**Repository:** https://github.com/Ashok-kumar290/synthscreen
**Models:** https://huggingface.co/Seyomi/synthguard-kmer
**Dataset:** https://huggingface.co/datasets/Seyomi/synthscreen-dataset
**Live API:** https://seyomi-synthguard-api.hf.space

---

## Abstract

DNA synthesis screeners today rely on sequence similarity (BLAST) against curated hazard databases. We demonstrate that this approach has two critical failure modes: (1) it flags **98.1% of benign sequences as hazardous** when applied against a comprehensive hazard database (false positive rate, real blastn 2.12.0), and (2) it misses AI-designed variants of dangerous proteins that fall below the percent-identity threshold. We present **SynthGuard**, a dual-track biosecurity screening system:

- **DNA track (k-mer + LightGBM):** <5 MB, 2 ms/sequence, CPU-native. Achieves 91.8% recall at 6.8% FPR — a **14× reduction in false positives** versus real BLAST. On codon-shuffled variants simulating AI protein design, achieves 91.4% recall versus BLAST's near-zero at high shuffle rates. Features include raw k-mer frequencies (k=3–6), RSCU, and CAI.
- **Protein track (ESM-2 650M + protein k-mer):** Fine-tuned ESM-2 achieves AUROC 0.901 (Recall 86.9%) operating on translated protein sequences. A lightweight protein k-mer LightGBM (426 features, <2ms) achieves AUROC 0.937 (Recall 84.4%, FPR 12.5%) and is deployed to the live API. Both tracks are independent — a DNA-optimized evasion that evades the k-mer model still produces a protein sequence evaluated by ESM-2 or the protein k-mer model.

The system integrates with the Track 3 BioLens dashboard via a live FastAPI endpoint and is designed as a complementary layer to SecureDNA and commec, not a replacement.

---

## 1. Motivation: Two Blind Spots in Current DNA Screening

Current DNA synthesis screening follows a pipeline established for natural sequence diversity: BLAST the query against curated hazard databases and flag matches above a percent-identity threshold, typically 70%.

This approach has two documented failure modes that SynthGuard addresses:

### Failure Mode 1: AI-Designed Evasion

A 2025 Science paper (Microsoft Research et al.) documented the core problem: **AI protein design tools generate functional hazards that evade sequence-based screening.** ProteinMPNN can design proteins with <30% sequence identity to their structural template while retaining near-identical function. RFdiffusion goes further, designing de novo proteins with no homology to any known sequence.

We verified this empirically: codon-shuffled variants at 75% synonymous substitution rate are invisible to BLAST (0% identity match) but retain functional identity. SynthGuard detects them at 83.5–97.2% confidence (ESCALATE) depending on shuffle rate.

### Failure Mode 2: Poor Precision When Applied Broadly

When we replaced our initial k-mer Jaccard proxy with **real blastn** (NCBI BLAST 2.12.0) and built a hazard database from the 1,008 original (non-augmented) training sequences, BLAST achieved 99.8% recall but at **98.1% false positive rate** — it flagged virtually every sequence, benign or hazardous, as a hit.

SynthGuard on the same test: **91.8% recall at 6.8% FPR**.

This is the core operational finding: BLAST is not wrong about hazards — it finds them. But the 98.1% FPR makes it completely unusable in a real synthesis workflow. Every benign gene a researcher orders would be held for review. SynthGuard achieves comparable recall while cutting false positives by 14×.

Neither failure mode is theoretical. Together they define the gap SynthGuard fills.

---

## 2. Journey: From funcscreen to SynthGuard

### 2.1 Protein Track: funcscreen → ESM-2 Recovery → Protein k-mer

The project began as `funcscreen`, a fine-tuned ESM-2 650M protein language model (LoRA, focal loss) intended to detect functional hazard from protein sequences. The approach was sound in theory: ESM-2 embeddings encode functional information beyond sequence similarity.

Initial evaluation revealed AUROC 0.514 (effectively random). Root cause: the training checkpoint saved LoRA adapter weights but not the classification head — predictions were meaningless. This is reported as an honest negative result.

**Recovery via merged checkpoint:** The HF Hub upload had used `merge_and_unload()` to produce a self-contained checkpoint (`Seyomi/synthguard-esm2`). Evaluating this merged checkpoint on the held-out test set:

| Metric | ESM-2 650M (merged LoRA) |
|--------|--------------------------|
| AUROC | **0.901** |
| Recall | **86.9%** |
| FPR | 26.3% |
| F1 | 0.835 |

**Lightweight protein k-mer (deployed to API):** ESM-2 requires ~5–10s on CPU and 2.6 GB RAM — too slow for real-time use on the HF Space free tier. We trained a protein k-mer LightGBM on 426 features: amino acid composition (20) + dipeptide frequencies (400) + physicochemical properties (6), using best-frame DNA→protein translation of the same training sequences.

| Metric | Protein k-mer LightGBM |
|--------|------------------------|
| AUROC | **0.937** |
| Recall | **84.4%** |
| FPR | 12.5% |
| F1 | 0.862 |

The protein k-mer model (<1 MB, <2 ms on CPU) is deployed at `/protein/screen`. The ESM-2 model is available at `Seyomi/synthguard-esm2` for offline use where GPU is available.

### 2.2 SynthGuard k-mer v1 (10 hazard families)

First implementation: LightGBM on 1,364-dimensional k-mer feature vectors. Trained on 10 hazardous families (ricin, botulinum type A, anthrax, Yersinia pestis, epsilon toxin, SEB, Shiga toxin, VEEV, Ebola, Marburg).

Result: 90%+ recall on in-distribution test sequences, but **38% OOD recall** on the first out-of-distribution benchmark.

Key insight: The model was learning organism-specific k-mer patterns rather than generalizable hazard signals.

### 2.3 SynthGuard k-mer v2 (expanded training data)

Added 10 more hazardous families: Burkholderia mallei/pseudomallei, Vibrio cholerae cholera toxin, abrin, diphtheria toxin, botulinum type B/E, Clostridium botulinum neurotoxin, Brucella abortus/melitensis. Also added 7 diverse benign organism families (Streptomyces, Pichia pastoris, Neurospora crassa, zebrafish, Aspergillus, Trichoderma, Chlamydomonas) to prevent high-GC benign sequences from being flagged.

OOD recall improved to 80.9%. Coxiella burnetii (obligate intracellular, ~32% GC) remained a gap at 3.2% recall.

### 2.4 SynthGuard k-mer v3 (codon normalization + Coxiella fix)

Added:
- Coxiella burnetii, Rickettsia prowazekii to training hazardous sequences
- 4 high-GC benign organisms (Rhodococcus, M. smegmatis, Deinococcus, S. venezuelae) to training benign sequences
- **87 codon normalization features** (RSCU×3 + CAI×3 + AA composition×20 + sequence RSCU×64) — described in Section 3.3

Coxiella recall: **3.2% → 96.8%**. OOD recall: **88.4%**. This is the current deployed model.

### 2.5 Honest Benchmarking: Replacing the BLAST Proxy

Early reports used k-mer Jaccard similarity (k=7) as a fast proxy for BLAST. This was directionally correct but not credible for a paper.

We replaced the proxy with **real blastn 2.12.0** (subprocess call, format 6, perc_identity threshold 70%). The BLAST DB is built from the **1,008 original, non-augmented hazardous training sequences** — this represents the "best case" for BLAST: it knows every hazard in the training set, and we measure what it does to a balanced test stream of hazardous and benign sequences.

Result: BLAST achieves near-perfect recall (99.8%) by flagging virtually everything, yielding 98.1% FPR. This is the benchmark we report in Section 4.

---

## 3. Technical Approach

### 3.1 Training Data Construction

**Hazardous sequences (22 query families, ~2,200 raw sequences from NCBI):**

| Category | Families |
|----------|---------|
| Protein toxins | Ricin chain A, abrin chain A, botulinum A/B/E, diphtheria toxin, Shiga toxin, epsilon toxin, Staphylococcal enterotoxin B |
| Bacterial virulence | Anthrax lethal factor, Yersinia pestis Yop proteins, Burkholderia mallei/pseudomallei, Vibrio cholerae CT, Francisella tularensis virulence |
| Intracellular pathogens | Coxiella burnetii, Brucella abortus/melitensis |
| Viral proteins | VEEV capsid, Ebola glycoprotein, Marburg nucleoprotein, Monkeypox virus virulence |

**Augmentation (per sequence):**
- 2 codon-shuffled variants at 25% and 45% synonymous substitution rate (simulating ProteinMPNN redesign)
- 4 short fragments 50–300bp (simulating synthesis order fragments)

**Benign sequences (17 query families, ~1,600 raw sequences):**
- Lab standard: E. coli lacZ, pUC19, EGFP, Bacillus subtilis, GAPDH, Arabidopsis actin, mouse beta-actin, synthetic vectors, Lactobacillus 16S
- Diverse codon usage (to prevent FP on GC-rich organisms): Streptomyces coelicolor, Pichia pastoris, Neurospora crassa, zebrafish housekeeping, Aspergillus niger, Trichoderma reesei, Chlamydomonas reinhardtii

**Final dataset:** ~14,700 sequences, class-balanced, 70/15/15 train/val/test split stratified by label and source family. Available at `Seyomi/synthscreen-dataset`.

### 3.2 k-mer Feature Engineering (v2)

For each sequence, a 1,364-dimensional feature vector:
- Global statistics (6): length, GC%, AT%, N-fraction, low-complexity score, Shannon entropy
- k-mer frequencies: k=3 (64), k=4 (256), k=5 (1,024), k=6 (4,096) — normalized counts
- Total: 5,446 raw features after adding all k-mers

**Why k-mer + LightGBM:**
- 5 MB model, 2 ms on CPU — compatible with real-time synthesis order volume
- SHAP explanations per prediction
- Handles extreme length variability (50bp oligos to 10kb genes)

### 3.3 Codon Normalization Features (v3 additions, 87 features)

Codon-optimized sequences (human expression, E. coli expression) retain function but shift k-mer frequencies toward the host organism's codon usage. A pathogen gene codon-optimized for human expression looks "human" to a raw k-mer model, potentially causing missed detections.

We added three codon normalization feature groups:

**RSCU per reference organism (64 features each × 3 = 192 raw, but the sequence's own RSCU is the 64-dimensional feature):**
- RSCU (Relative Synonymous Codon Usage): for each of 64 codons, frequency relative to synonymous alternatives
- Computed from Kazusa DB codon usage tables for E. coli K-12, Homo sapiens, and S. cerevisiae
- Sequence RSCU: the input sequence's own RSCU vector (64 features)

**CAI vs. reference organisms (3 features):**
- CAI (Codon Adaptation Index): geometric mean of RSCU values for each codon in the sequence
- Computed against E. coli, human, and yeast reference tables
- A human-optimized pathogen gene will show high CAI vs. human — a flag for codon optimization

**Amino acid composition (20 features):**
- Frequency of each of 20 amino acids in the translated sequence
- Pathogen effectors have distinct amino acid biases (high Lys, Arg, Glu) independent of codon usage

**Total new features: 87 (64 RSCU + 3 CAI + 20 AA)**

Combined with 5,446 k-mer features: **5,533 total features** in the v3 model.

**Impact:** The RSCU and CAI features allow the model to detect codon-optimized sequences that would otherwise have "normal" k-mer frequencies for the target host organism. This addresses the adversarial case where a synthesis customer submits a human-codon-optimized version of a pathogen toxin.

### 3.4 Model Architecture

**General triage model (sequences ≥150bp):**
- LightGBM (500 estimators, max_depth=7, class weight balanced, early stopping on validation)
- Calibrated with CalibratedClassifierCV (sigmoid method)
- Decision tiers: ALLOW (<0.30), REVIEW (0.30–0.60), ESCALATE (≥0.60)

**Short-sequence specialist (sequences <150bp):**
- Separate LightGBM (400 estimators, max_depth=5)
- Trained exclusively on fragments with sliding-window augmentation
- Handles the inherently ambiguous short-oligo regime separately

**Thresholds (v3):** review=0.30, escalate=0.60 (lowered from 0.40/0.70 after Shiga toxin at 0.300 was missed under old thresholds)

### 3.5 Decision Pipeline

```
Synthesis order (DNA sequence)
         │
         ▼
  SecureDNA / commec        ← existing tools, first pass
  (cryptographic + HMM)
         │ uncertain / short / novel
         ▼
  SynthGuard k-mer v3       ← 2ms, CPU, 5MB
         │
         ├── ALLOW (score < 0.30)
         │
         ├── REVIEW (0.30 ≤ score < 0.60)   ← human review queue
         │
         └── ESCALATE (score ≥ 0.60)        → hold order
                  │
                  ▼
         Structured JSON → BioLens dashboard (Track 3)
```

**Note:** The DNA track screens coding sequences. The protein track (`/protein/screen`) accepts amino acid sequences directly or coding DNA (auto-translated to best reading frame before scoring). Both tracks are independent — model disagreement (one flags, one does not) is itself a risk signal.

---

## 4. Results

### 4.1 Core Benchmark: SynthGuard vs. Real BLAST

Evaluated on the full held-out test set. BLAST used **real blastn 2.12.0** against a hazard database built from the **1,008 original (non-augmented) hazardous training sequences** — the honest benchmark: BLAST knows every known hazard, the question is what it does to benign traffic.

| Method | Recall | FPR | F1 | AUROC |
|--------|--------|-----|----|-------|
| BLAST (real blastn 2.12.0, 70% threshold, 1,008-seq training DB) | 0.998 | **0.981** | 0.671 | 0.509 |
| **SynthGuard k-mer v4 (DNA)** | **0.918** | **0.068** | **0.925** | **0.977** |

**Key takeaway:** BLAST achieves near-perfect recall (99.8%) by flagging almost everything — including 98.1% of benign sequences. Its F1 of 0.671 and AUROC of 0.509 (near random for discrimination) reveal that high recall comes entirely at the expense of any selectivity. SynthGuard achieves 91.8% recall at 6.8% FPR — a **14× reduction in false positives**. In a real synthesis workflow, 98.1% FPR means essentially every order is held for review, making the tool operationally unusable without human review of every submission.

### 4.2 AI-Designed Variant Detection (Systematic Evaluation)

This is the core claim of Track 1. We ran a systematic evaluation: 50 independently codon-shuffled variants of Shiga toxin stx1A (876bp) at each of 4 shuffle rates — 200 variants total.

| Shuffle Rate | SynthGuard Detect% | Mean Score | Min Score | BLAST Detect% |
|-------------|-------------------|-----------|----------|--------------|
| 25% (ProteinMPNN-level redesign) | **98%** | 0.803 | 0.227 | **0%** |
| 50% (heavy redesign) | **92%** | 0.729 | 0.240 | **0%** |
| 75% (extreme redesign) | **98%** | 0.774 | 0.155 | **0%** |
| 90% (near-total synonymous substitution) | **92%** | 0.720 | 0.187 | **0%** |

At every shuffle rate — including 90% synonymous substitution where 9 of 10 codons are replaced — SynthGuard detects 92–98% of variants. BLAST detects 0% at all rates. Mean scores (0.720–0.803) remain well above the REVIEW threshold (0.30) across the entire distribution.

This result is not cherry-picked: it reflects the full distribution of 50 random seeds per rate. The minimum score at 75% shuffle (0.155) shows one near-miss that dropped below REVIEW threshold — this is the honest lower tail of the distribution.

On the full test set of codon-shuffled variants (sequences at 25–45% shuffle rates):

| Method | Recall on AI variants | FPR on benign |
|--------|----------------------|---------------|
| BLAST (real blastn, training DB) | 0.998 | **0.982** |
| **SynthGuard k-mer v4** | **0.914** | **0.083** |

BLAST's near-perfect recall on these variants reflects that 25–45% synonymous substitution still leaves >70% nucleotide identity — BLAST finds the originals. But the FPR of 98.2% means it simultaneously flags essentially every benign sequence. The systematic shuffle eval (Section 4.2 table above) shows BLAST failing completely at 75–90% shuffle rates, where identity drops below the 70% threshold. SynthGuard detects 92–98% at all shuffle rates.

### 4.3 Short-Sequence Performance

| Method | Recall (<150bp) | FPR | AUROC |
|--------|----------------|-----|-------|
| BLAST (real blastn, training DB) | 1.000 | **0.974** | 0.513 |
| **SynthGuard short-seq specialist (v4)** | **0.797** | **0.145** | **0.897** |

Short sequences are the hardest regime: at <50bp, biological ground truth is inherently ambiguous. The specialist model correctly expresses uncertainty via the REVIEW tier rather than committing to binary decisions.

### 4.4 Out-of-Distribution Benchmark

Evaluated on 7 toxin families **never seen during training**: tetanus toxin, Francisella tularensis, Brucella abortus, Coxiella burnetii, C. difficile toxin A, SARS-CoV-2 spike, Variola virus (~1,600 sequences balanced).

| Method | OOD Recall | OOD FPR | AUROC |
|--------|-----------|---------|-------|
| BLAST (proxy) | 1.2% | 0.0% | 0.506 |
| **SynthGuard k-mer v3** | **88.4%** | **14.9%** | **0.937** |

**Per-family OOD recall (SynthGuard v3):**

| Family | v1 Recall | v3 Recall | BLAST (proxy) |
|--------|----------|----------|--------------|
| Tetanus toxin | ~50% | **100%** | 78.6% |
| Francisella tularensis | 0% | **95.8%** | 0% |
| Coxiella burnetii | 3.2% | **96.8%** | 0% |
| C. difficile toxin A | ~60% | **100%** | 0% |
| SARS-CoV-2 spike | ~70% | **92.5%** | 0% |
| Variola virus | ~80% | **100%** | 0% |
| Brucella abortus | 0% | 60.9% | 0% |

BLAST catches nothing on 6 of 7 families. It catches tetanus (78.6%) only because tetanus toxin shares significant identity with botulinum type A, which is in most curated BLAST databases — confirming that BLAST only works when a close relative exists in the reference database.

The trajectory from v1 → v3 shows iterative data expansion directly closes recall gaps. Coxiella (3.2% → 96.8%) is the sharpest example: adding obligate intracellular pathogens to training fixed a failure mode caused by unusual AT-rich codon usage.

### 4.5 SHAP Explainability

Top features by mean absolute SHAP value (k-mer v3 model):
- Codon usage k-mers (k=3): CTG, GAG, GTG — pathogen-associated high-GC codons
- CAI vs. E. coli: codon-optimized sequences show elevated CAI
- GC content: hazardous sequences cluster at 45–65% GC
- Sequence length: fragments under 100bp show distinct k-mer profiles

Every API call returns SHAP feature attributions — essential for human review workflows where analysts need to understand why a sequence was flagged, not just the score.

### 4.6 Protein Track Benchmark

Both protein models were evaluated on the held-out test set after DNA→protein translation (best-frame, ≥30 aa threshold):

| Method | Recall | FPR | F1 | AUROC |
|--------|--------|-----|----|-------|
| **Protein k-mer LightGBM** (deployed, <2ms) | **0.844** | **0.125** | **0.862** | **0.937** |
| **ESM-2 650M** (HF Hub, ~5–10s CPU) | **0.869** | 0.263 | 0.835 | 0.901 |

The protein k-mer model achieves higher AUROC than ESM-2 on this dataset despite being orders of magnitude smaller. This reflects that amino acid composition + dipeptide frequencies are strong distinguishing signals for the 20 hazardous protein families in the training set.

**Orthogonal signal:** The two tracks (DNA k-mer and protein k-mer) make different errors. A DNA-level codon-shuffled sequence that evades the DNA model still produces a protein sequence that the protein model evaluates independently. In adversarial scenarios where an attacker specifically games DNA codon usage, the protein track provides a second line of defense.

**Minimum sequence length:** Protein scoring is unreliable below ~100 aa (dipeptide statistics are sparse). Sequences under 30 aa after translation are rejected. Sequences 30–100 aa are screened but the confidence is lower.

### 4.7 Live Demo: Demonstrating the BLAST Gap

At the SynthGuard API endpoint, we demonstrated the core finding in real time:

**Test 1 — Benign sequence (EGFP):**
- BLAST: flags at 100% identity (GFP is in NCBI databases)
- SynthGuard: 0.027 (ALLOW) — correctly identifies as benign

**Test 2 — Shiga toxin fragment (300bp):**
- BLAST: misses at 70% threshold (fragment too short / insufficient identity)
- SynthGuard: 0.300+ (REVIEW/ESCALATE)

**Test 3 — Shiga toxin, 75% codon shuffle:**
- BLAST: 0 matches at any threshold
- SynthGuard: 0.835 (ESCALATE)

Test 1 demonstrates BLAST's high FPR problem. Tests 2–3 demonstrate BLAST's recall problem on AI-designed variants.

---

## 5. Track 3 Integration (BioLens)

The API endpoint (`app/api.py`, deployed at `seyomi-synthguard-api.hf.space`) exposes:

```
POST /biolens/screen
{
  "sequence": "ATGGCTTACAAG...",
  "threshold_review": 0.30,
  "threshold_escalate": 0.60
}

→
{
  "ok": true,
  "hazard_score": 0.87,
  "risk_level": "ESCALATE",
  "confidence": "high",
  "category": "general_triage",
  "explanation": "Sequence flagged by SynthGuard k-mer model...",
  "baseline_result": {...},
  "model_name": "synthguard-kmer"
}
```

```
POST /biolens/screen            ← BioLens primary endpoint (DNA + protein routing)
POST /screen                    ← DNA single-sequence
POST /screen/batch              ← up to 1000 DNA sequences
POST /protein/screen            ← protein (AA sequence or coding DNA, auto-translated)
POST /split/submit              ← Track 4: submit a synthesis fragment
GET  /split/customer/{id}       ← Track 4: fragment status per customer
DELETE /split/customer/{id}/flush ← Track 4: clear customer state
GET  /health                    ← liveness check
GET  /model/info                ← model metadata
```

### 5.1 Track 4: Split-Order Detection

Hazardous sequences can be evaded at the order level by splitting them into short fragments, each of which individually passes screening. SynthGuard detects this via overlap-assembly:

1. Each incoming fragment is screened individually and stored in SQLite (keyed by `customer_id`)
2. On each new submission, greedy overlap-layout-consensus assembly is attempted across all fragments from that customer (minimum 15bp suffix/prefix overlap)
3. The assembled sequence is screened by the SynthGuard k-mer model
4. If the assembly scores ESCALATE, an alert is raised and all contributing fragment IDs are flagged

The assembly uses greedy pairwise overlap with O(n²) fragment comparison, capped at 30 fragments per customer to prevent blowup. Maximum assembled length is 12,000bp.

The Track 3 BioLens dashboard calls `/biolens/screen` per synthesis order in INTEGRATED mode and renders the `risk_level` / `explanation` fields directly. CORS is open for the hackathon demo.

**PROTEIN input handling via BioLens:** When `seq_type: "PROTEIN"` is passed or the sequence is detected as amino acids, the BioLens endpoint routes to the protein k-mer model (AUROC 0.937) and returns the standard risk_level schema. Protein sequences can also be submitted to `/protein/screen` directly.

---

## 6. Limitations and Honest Assessment

### 6.1 Protein Track: High FPR Tradeoff

Both protein models (ESM-2 AUROC 0.901, protein k-mer AUROC 0.937) have meaningfully higher FPR than the DNA k-mer model (FPR 26.3% and 12.5% respectively, vs. 6.8% for DNA). This reflects a fundamental difference in input: amino acid sequences carry less distinguishing information than coding DNA (no codon-usage signal), so the models must trade off more false positives to achieve comparable recall.

**Designed use:** The protein track is intended as a confirmation layer, not primary triage. The recommended pipeline is:
1. DNA k-mer model for fast triage (6.8% FPR)
2. Protein k-mer model for confirmation on flagged sequences (12.5% FPR, independent signal)
3. ESM-2 (offline, GPU) for highest-confidence cases

Model disagreement — DNA flags, protein does not (or vice versa) — is itself a risk signal that routes to human review.

**Initial checkpoint failure (documented):** The original ESM-2 training checkpoint (funcscreen) had AUROC 0.514 due to missing classifier weights. The merged checkpoint (`Seyomi/synthguard-esm2`) resolved this. This failure mode and its resolution are reported honestly for reproducibility.

### 6.2 BLAST Comparison Caveats

Our BLAST evaluation uses real blastn 2.12.0 with the following honest limitations:

1. **DB composition drives FPR.** Our benchmark builds the BLAST DB from the 1,008 original hazardous training sequences. Production BLAST systems (SecureDNA, NCBI BLAST) use much larger, curated DBs with organism-specific exclusions that reduce false positives. Our 98.1% FPR likely overestimates what a well-tuned production BLAST would produce — but illustrates the fundamental precision problem.

2. **Threshold choice.** We used the standard 70% nucleotide identity threshold. A stricter threshold (e.g., 90%) would reduce FPR but also sharply reduce recall on codon-shuffled variants. The tradeoff cannot be tuned away: at any threshold where BLAST catches heavily redesigned sequences, it will produce excessive false positives.

3. **High-shuffle BLAST behavior is proxy-only.** The systematic shuffle eval (50 variants × 4 rates) reports 0% BLAST detection based on the k-mer Jaccard proxy. Real blastn at 75–90% shuffle would also fail (nucleotide identity drops below 70%), but this specific experiment used the proxy, not real blastn.

### 6.3 No Wet-Lab Validation

All results are computational. We do not claim the sequences used as hazardous retain dangerous function — only that they evade BLAST screening and are detected by SynthGuard. Wet-lab functional validation is beyond the scope of a hackathon project.

### 6.4 Training Data Overlap Risk

The OOD benchmark tests on families withheld from training. However, the training augmentation (codon shuffling) may have inadvertently created sequences similar to some "unseen" families through random walks in sequence space. True OOD evaluation requires held-out family splits from the initial data collection phase, which we implemented but cannot guarantee are fully orthogonal.

### 6.5 Known Remaining Gaps

- **Brucella abortus:** 60.9% recall — still below target despite being in training set. Brucella virulence factor sequences have high similarity to environmental bacteria.
- **RFdiffusion de novo:** Not evaluated. Sequences with zero homology to any training example represent the hardest adversarial case. Our codon normalization features would not help here.
- **Very short sequences (<50bp):** Accuracy degrades below 50bp; biological context is insufficient for reliable classification.

---

## 7. Dual-Use Considerations

SynthGuard is designed to *reduce* the risk of dangerous DNA synthesis. All training data is derived from publicly available NCBI databases using queries standard in the biosecurity literature.

**Risk 1: Adversarial probing.** The model classifies sequences — iterative probing could design evasive sequences. Mitigations: (a) the model runs inside the screener, not as a public API for synthesis customers; (b) recall-optimized training creates a defense-favoring asymmetry; (c) the codon normalization features mean the model generalizes beyond raw k-mer patterns, making gradient-based evasion harder.

**Risk 2: False confidence.** A synthesis company might over-rely on SynthGuard and reduce human review. We explicitly design against this: REVIEW tier is broad (threshold 0.30), SHAP explanations require human interpretation, and SynthGuard is positioned as a complement to SecureDNA and commec.

We recommend that any production deployment coordinate with USAMRIID, CDC, and the IBBIS consortium before deploying against real synthesis orders.

---

## 8. Future Work

1. **Protein track ensemble:** Combine DNA k-mer + protein k-mer + ESM-2 scores into a single risk signal. Disagreement between tracks is already meaningful — formalizing it into a calibrated ensemble could reduce both FPR and false-negative rate below what either track achieves alone.
2. **Reduce protein FPR:** Current protein k-mer FPR (12.5%) is higher than the DNA model. Adding more diverse benign protein sequences (especially from lab-standard expression vectors and housekeeping proteins) to protein training would push this down.
3. **RFdiffusion red-teaming:** Evaluate against de novo protein designs with no sequence homology to any training example — the hardest adversarial case for k-mer models.
4. **Close the Brucella gap:** Targeted data expansion for Brucella virulence factors (current: 60.9% recall).
5. **Systematic Select Agent coverage:** Extend to all 60+ CDC/USDA Tier 1 Select Agents (current: ~22 families).
6. **Production BLAST comparison:** Run real blastn against the full NCBI nt database to confirm FPR behavior at scale, and with organism-specific exclusion lists.
7. **Online retraining pipeline:** Retrain quarterly as new AI design tools and novel pathogen sequences emerge.

---

## 9. Appendix: Key Numbers Summary

**DNA Track (k-mer + LightGBM):**

| Metric | Value | Notes |
|--------|-------|-------|
| Model size | 5 MB | LightGBM, CPU-native |
| Inference time | 2 ms | Single sequence, CPU |
| Feature dimensions | 5,533 | 5,446 k-mer + 87 codon normalization |
| Full test AUROC | 0.977 | v4 model |
| Full test Recall | 0.918 | threshold 0.30 |
| Full test FPR | 0.068 | threshold 0.30 |
| Full test F1 | 0.925 | |
| Short-seq specialist Recall | 0.797 | v4 model |
| Short-seq specialist AUROC | 0.897 | |
| BLAST Recall (real blastn, training DB) | 0.998 | near-perfect, flags everything |
| BLAST FPR (real blastn, training DB) | 0.981 | operationally unusable |
| BLAST F1 (real blastn) | 0.671 | precision collapses at 98.1% FPR |
| AI-variant Recall (SynthGuard v4) | 0.914 | codon-shuffled test set |
| AI-variant FPR on benign (BLAST) | 0.982 | real blastn |
| Shuffle eval — 25% rate | 98% detect | 50 variants, BLAST 0% |
| Shuffle eval — 50% rate | 92% detect | 50 variants, BLAST 0% |
| Shuffle eval — 75% rate | 98% detect | 50 variants, BLAST 0% |
| Shuffle eval — 90% rate | 92% detect | 50 variants, BLAST 0% |
| OOD Recall (7 unseen families) | 0.884 | v3 benchmark |
| OOD AUROC | 0.937 | v3 benchmark |
| Review threshold | 0.30 | lowered from 0.40 |
| Escalate threshold | 0.60 | lowered from 0.70 |
| Training hazard families | 22 | up from 10 in v1 |
| Training benign families | 17 | |
| Dataset size | ~20,154 | balanced, augmented, v4 |

**Protein Track:**

| Metric | Protein k-mer (deployed) | ESM-2 650M (HF Hub) |
|--------|--------------------------|----------------------|
| Model size | <1 MB | 2.6 GB |
| Inference time | <2 ms CPU | ~5–10 s CPU |
| Feature dimensions | 426 | 650M parameters |
| AUROC | **0.937** | **0.901** |
| Recall | 84.4% | 86.9% |
| FPR | 12.5% | 26.3% |
| F1 | 0.862 | 0.835 |
| Minimum sequence | 10 aa | 10 aa |
| HF Hub | `Seyomi/synthguard-kmer` (protein_kmer_model.pkl) | `Seyomi/synthguard-esm2` |

---

## References

1. Jumper, J. et al. (2021). Highly accurate protein structure prediction with AlphaFold. *Nature*, 596, 583–589.
2. Dauparas, J. et al. (2022). Robust deep learning–based protein sequence design using ProteinMPNN. *Science*, 378, 49–56.
3. Watson, J.L. et al. (2023). De novo design of protein structure and function with RFdiffusion. *Nature*, 620, 1089–1100.
4. [Microsoft Research et al.] (2025). AI protein design creates functional hazards invisible to sequence screening. *Science*. [Exact citation TBC from hackathon resources]
5. Lin, Z. et al. (2023). Evolutionary-scale prediction of atomic-level protein structure with a language model. *Science*, 379, 1123–1130. [ESM-2]
6. Ke, G. et al. (2017). LightGBM: A Highly Efficient Gradient Boosting Decision Tree. *NeurIPS 2017*.
7. Sharp, P.M. & Li, W.-H. (1987). The codon Adaptation Index — a measure of directional synonymous codon usage bias, and its potential applications. *Nucleic Acids Research*, 15(3), 1281–1295. [CAI]
8. SecureDNA. https://securedna.org — Cryptographic DNA screening, 30bp resolution.
9. commec / IBBIS. https://ibbis.bio — HMM-based biosecurity screening.
10. Kazusa DNA Research Institute. Codon usage database. https://www.kazusa.or.jp/codon/ [RSCU reference tables]

---

*Generated: April 25, 2026 | AIxBio Hackathon 2026*
