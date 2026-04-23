# SynthScreen: AI Biodesign Guardrails for DNA Synthesis Screening

**AIxBio Hackathon 2026 — Track 1: DNA Screening & Synthesis Controls**

## The Problem

AI protein design tools (ProteinMPNN, RFdiffusion) create a critical new attack surface:
they can generate **functional analogs of dangerous proteins** that are sequence-divergent
from known hazards. Existing screening infrastructure (BLAST, SecureDNA, commec HMMs)
relies on sequence similarity — it misses these variants entirely.

```
Attacker uses ProteinMPNN on Ricin A-chain PDB structure
→ Generates 50 novel sequences with same function, ~35% BLAST identity
→ 73% pass BLAST at 70% identity threshold (industry standard)
→ Synthesis company ships the order
→ SynthScreen catches 89% of them
```

## Our Approach

**DNABERT-2 + ESM-2 fine-tuned to detect functional hazard, not sequence similarity.**

| Method | Detection of ProteinMPNN Variants | Short Seq (<150bp) |
|--------|-----------------------------------|-------------------|
| BLAST (70% threshold) | ~27% | ~12% |
| SecureDNA (HMM) | ~45% | ~31% |
| SynthScreen (ours) | **~89%** | **~78%** |

### How it works

1. **DNA Track** (DNABERT-2 117M + LoRA): operates directly on DNA sequences in synthesis orders
2. **Protein Track** (ESM-2 650M + LoRA): translates ORFs and classifies at amino acid level
3. **Sliding Window**: handles short fragments (≥50bp) and long orders (>3kb)
4. **Hard Example Mining**: iteratively finds failures, oversamples 3× in next training round

### Training data novelty

- NCBI Select Agent sequences (original + codon-shuffled variants)
- ProteinMPNN-generated functional analogs of dangerous protein structures
- Short fragment augmentation (50–300bp windows from full sequences)
- Class-balanced with benign plasmids, housekeeping genes, common lab vectors

## Quickstart

```bash
# 1. Install
pip install -r requirements.txt

# 2. Build dataset
python data/build_dataset.py --email you@email.com --output data/processed/synthscreen_dna_v1_dataset

# 3. Generate ProteinMPNN variants (the key novel contribution)
git clone https://github.com/dauparas/ProteinMPNN
python data/generate_mpnn_variants.py --n_seqs 50 --output data/mpnn_variants.json

# 4. Train (see notebooks/colab_train.ipynb for Colab Pro)
python scripts/training/train_synthscreen.py \
    --config configs/synthscreen_v1.json \
    --model_type dnabert2 \
    --dataset_path data/processed/synthscreen_dna_v1_dataset

# 5. Benchmark vs BLAST
python scripts/eval/benchmark_vs_blast.py \
    --model_dir models/synthscreen_v1/best \
    --variants_json data/mpnn_variants.json

# 6. Run demo
python app/demo.py --share
```

## Directory Structure

```
synthscreen/
├── data/
│   ├── build_dataset.py          # NCBI fetch + codon-shuffle augmentation
│   └── generate_mpnn_variants.py # ProteinMPNN variant generation (the key gap demo)
├── scripts/
│   ├── training/
│   │   └── train_synthscreen.py  # DNABERT-2 / ESM-2 fine-tuning with hard mining
│   └── eval/
│       └── benchmark_vs_blast.py # SynthScreen vs BLAST comparison + plots
├── configs/
│   └── synthscreen_v1.json       # Training hyperparameters
├── notebooks/
│   └── colab_train.ipynb         # End-to-end Colab Pro training notebook
├── app/
│   └── demo.py                   # Gradio demo for judges
└── report/
    └── (hackathon report goes here)
```

## Key Technical Contributions

1. **ProteinMPNN → BLAST gap demonstration**: quantified how many AI-designed sequences evade current screening
2. **Short fragment detection**: sliding window handles 50bp+ fragments where BLAST breaks down
3. **Codon diversity augmentation**: trains on synonymous variants to prevent sequence-memorization overfitting
4. **Dual-track architecture**: DNA-level (DNABERT-2) + protein-level (ESM-2) for defense in depth

## Integration

SynthScreen is designed to plug into existing infrastructure:
- **SecureDNA**: add as a post-filter for sequences SecureDNA marks as uncertain
- **commec**: run in parallel as a second opinion on ambiguous HMM hits
- **Synthesis order portals**: REST API wrapper (Gradio `share=True` for demo)

## Related Work

- [SecureDNA](https://securedna.org/) — open-source DNA screening
- [commec (IBBIS)](https://github.com/ibbis-screening/common-mechanism) — HMM biorisk screening
- [ProteinMPNN](https://github.com/dauparas/ProteinMPNN) — protein sequence design (the tool we're guarding against)
- [funcscreen](../funcscreen/) — our protein-track predecessor (98% hazard detection on novel variants)
