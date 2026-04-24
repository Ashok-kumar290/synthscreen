# Expression of Interest — Coefficient Giving Biosecurity RFP
**Deadline: May 11, 2026 | bio-rfp@coefficientgiving.org**

---

## SynthScreen: Closing the AI Biodesign Gap in DNA Synthesis Screening

### The Problem (100 words)

AI protein design tools — ProteinMPNN, RFdiffusion, AlphaFold 3 — have fundamentally changed
the biosecurity landscape. These tools can now design functional analogs of dangerous proteins
that share minimal sequence similarity with known hazards. Our experiments show that **99.6% of
ProteinMPNN-generated variants of known Select Agent toxins pass BLAST at the industry-standard
70% identity threshold** — the core algorithm used by every major DNA synthesis screener today.
Current tools (SecureDNA, commec) were designed for natural sequence diversity, not AI-generated
diversity. A new layer of defense is needed.

### Our Solution (150 words)

SynthScreen is a machine learning screening layer that detects **functional hazard**
rather than sequence similarity. We train SynthGuard, a dual-track system (DNA k-mer + ESM-2
protein), using a dataset specifically constructed to include:

- Codon-shuffled variants of known dangerous genes (simulating AI optimization for expression)
- ProteinMPNN-generated sequences from dangerous protein structures (Ricin, BoNT, anthrax LF)
- Short fragment augmentation (50–300bp windows — the fragmented-order attack vector)

Our evaluation on held-out sequences shows:

| Method | AI-variant Recall | Full-set AUROC |
|--------|-------------------|----------------|
| BLAST (70% threshold) | 0.4% | 0.503 |
| **SynthGuard k-mer (DNA)** | **90.7%** | **0.970** |
| **SynthGuard ESM-2 (protein)** | **89.6%** | **0.916** |

The lightweight k-mer LightGBM model (5MB, 2ms/sequence, CPU-native) outperforms BLAST by
**227× on AI-designed variants**. On short fragments (<150bp) where BLAST catches 0%, SynthGuard
reaches 85.4% recall. In an out-of-distribution benchmark on 7 toxin families *never seen during
training* (tetanus, Francisella, Brucella, Coxiella, C. diff, SARS-CoV-2, Variola), the model
achieves **80.9% recall vs. 1.2% for BLAST** — a 65× improvement. SHAP analysis confirms the
model detects codon-usage signatures intrinsic to pathogen genomes rather than memorizing known
sequences, explaining its generalization to unseen AI-designed variants.

This directly addresses the stated Track 1 gap: *"current screening misses AI-designed
protein variants and struggles with short sequences."*

### What Funding Would Unlock (150 words)

The hackathon prototype demonstrates proof-of-concept on a curated dataset of ~14,700 sequences
across 37 organism families. Funding would enable:

**1. Production-grade training dataset** ($40K): Systematic generation of ProteinMPNN/RFdiffusion
variants for all CDC/USDA Tier 1 Select Agents, plus comprehensive short-fragment augmentation.
Partnership with structural biologists for validated dangerous structure benchmarks.

**2. Adversarial robustness evaluation** ($30K): Red-team the model with domain experts to find
failure modes. Commission biosecurity researchers to design sequences that evade SynthScreen.
Iterate training to close each gap (priority: Coxiella burnetii, AT-rich obligate intracellular
pathogens currently at 3.2% recall).

**3. Integration with SecureDNA / commec** ($20K): Build the API layer, write integration
documentation, work with SecureDNA team to deploy as a supplementary screening layer
for sequences flagged as uncertain.

**4. Sustained model updates** ($10K/year): As AI design tools improve, retraining pipeline
to keep pace — monthly retraining against new ProteinMPNN/RFdiffusion model releases.

**Total request: $100K Year 1**

### Team

- Ashok Kumar — ML lead (SynthGuard k-mer + ESM-2 fine-tuning, biosecurity ML)
- [Add teammates here]

### Models & Dataset

- DNA model: https://huggingface.co/Seyomi/synthguard-kmer
- Protein model: https://huggingface.co/Seyomi/synthguard-esm2
- Dataset: https://huggingface.co/datasets/Seyomi/synthscreen-dataset

### Repository

https://github.com/Ashok-kumar290/synthscreen

### Contact

asphaltultron@gmail.com
