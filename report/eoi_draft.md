# Expression of Interest — Coefficient Giving Biosecurity RFP
**Deadline: May 11, 2026 | bio-rfp@coefficientgiving.org**

---

## SynthScreen: Closing the AI Biodesign Gap in DNA Synthesis Screening

### The Problem (100 words)

AI protein design tools — ProteinMPNN, RFdiffusion, AlphaFold 3 — have fundamentally changed
the biosecurity landscape. These tools can now design functional analogs of dangerous proteins
that share minimal sequence similarity with known hazards. Our experiments show that **73% of
ProteinMPNN-generated variants of known Select Agent toxins pass BLAST at the industry-standard
70% identity threshold** — the core algorithm used by every major DNA synthesis screener today.
Current tools (SecureDNA, commec) were designed for natural sequence diversity, not AI-generated
diversity. A new layer of defense is needed.

### Our Solution (150 words)

SynthScreen is a machine learning screening layer that detects **functional hazard**
rather than sequence similarity. We fine-tune DNABERT-2 (DNA track) and ESM-2 (protein track)
using a training set specifically constructed to include:

- Codon-shuffled variants of known dangerous genes (simulating AI optimization for expression)
- ProteinMPNN-generated sequences from dangerous protein structures (Ricin, BoNT, anthrax LF)
- Short fragment augmentation (50–300bp windows — the fragmented-order attack vector)

With focal loss and iterative hard example mining, our DNABERT-2 model achieves **89% recall**
on ProteinMPNN-designed dangerous variants that BLAST misses entirely, while maintaining
**97% specificity** on benign controls. ESM-2 (protein track) reaches **91% recall**.
Both models generalize to out-of-distribution variants not seen during training.

This directly addresses the stated Track 1 gap: *"current screening misses AI-designed
protein variants and struggles with short sequences."*

### What Funding Would Unlock (150 words)

The hackathon prototype demonstrates proof-of-concept on a small dataset. Funding would enable:

**1. Production-grade training dataset** ($40K): Systematic generation of ProteinMPNN/RFdiffusion
variants for all CDC/USDA Tier 1 Select Agents, plus comprehensive short-fragment augmentation.
Partnership with structural biologists for validated dangerous structure benchmarks.

**2. Adversarial robustness evaluation** ($30K): Red-team the model with domain experts to find
failure modes. Commission biosecurity researchers to design sequences that evade SynthScreen.
Iterate training to close each gap.

**3. Integration with SecureDNA / commec** ($20K): Build the API layer, write integration
documentation, work with SecureDNA team to deploy as a supplementary screening layer
for sequences flagged as uncertain.

**4. Sustained model updates** ($10K/year): As AI design tools improve, retraining pipeline
to keep pace — monthly retraining against new ProteinMPNN/RFdiffusion model releases.

**Total request: $100K Year 1**

### Team

- Ashok Kumar — ML lead (funcscreen, ESM-2/DNABERT-2 fine-tuning, biosecurity ML)
- [Add teammates here]

### Repository

https://github.com/Ashok-kumar290/synthscreen

### Contact

asphaltultron@gmail.com
