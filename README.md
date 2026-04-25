# SynthGuard: Closing the AI Biodesign Gap in DNA Synthesis Screening

**AIxBio Hackathon 2026 — Track 1: DNA Screening & Synthesis Controls**
**Team:** Ashok Kumar
**Live API:** https://seyomi-synthguard-api.hf.space
**Model:** https://huggingface.co/Seyomi/synthguard-kmer
**Dataset:** https://huggingface.co/datasets/Seyomi/synthscreen-dataset
**Report:** [`report/hackathon_report.md`](report/hackathon_report.md)

---

## The Problem

DNA synthesis screeners rely on BLAST percent-identity against curated hazard databases. We measured two failure modes with real blastn 2.12.0:

1. **98.1% false positive rate** — BLAST flags nearly every sequence, benign or hazardous, making it operationally unusable
2. **0% detection of AI-designed variants** at ≥75% synonymous substitution — codon-optimized toxins evade identity thresholds entirely

SynthGuard is a k-mer + LightGBM triage model that achieves **91.8% recall at 6.8% FPR** — a 14× reduction in false positives versus real BLAST.

---

## Benchmark Results

**DNA Track:**

| Method | Recall | FPR | F1 | AUROC |
|--------|--------|-----|----|-------|
| BLAST (real blastn 2.12.0, 70% threshold) | 0.998 | **0.981** | 0.671 | 0.509 |
| **SynthGuard k-mer v4 (DNA)** | **0.918** | **0.068** | **0.925** | **0.977** |

**Protein Track:**

| Method | Recall | FPR | F1 | AUROC |
|--------|--------|-----|----|-------|
| **SynthGuard protein k-mer (deployed)** | **0.844** | **0.125** | **0.862** | **0.937** |
| **SynthGuard ESM-2 650M (HF Hub)** | **0.869** | **0.263** | **0.835** | **0.901** |

**AI-designed variant detection — DNA track (systematic evaluation — 50 variants × 4 shuffle rates):**

| Shuffle Rate | SynthGuard | BLAST |
|-------------|-----------|-------|
| 25% synonymous substitution | **98%** | 0% |
| 50% synonymous substitution | **92%** | 0% |
| 75% synonymous substitution | **98%** | 0% |
| 90% synonymous substitution | **92%** | 0% |

---

## What's Actually Built

**SynthGuard is a dual-track system.** The DNA k-mer model is the primary screener. The protein k-mer model (AUROC 0.937) and ESM-2 650M (AUROC 0.901) are the protein track — operating independently on translated sequences. An initial ESM-2 checkpoint (funcscreen) evaluated at AUROC 0.514 due to missing classifier weights in the checkpoint; the merged version on HF Hub is functional.

### Features (5,533 total)
- **k-mer frequencies** k=3–6 (5,446 features)
- **RSCU** — Relative Synonymous Codon Usage (64 features): detects codon-optimized sequences
- **CAI** — Codon Adaptation Index vs E. coli, human, yeast (3 features)
- **Amino acid composition** (20 features): pathogen-specific AA biases independent of codon usage

### Models
- **General triage model** (LightGBM, sequences ≥150bp): AUROC 0.977
- **Short-seq specialist** (LightGBM, sequences <150bp): AUROC 0.897
- **Track 4 split-order detection**: greedy overlap assembly of fragments per customer, alerts on assembled ESCALATE

### Decision tiers
- `ALLOW` — risk score < 0.30
- `REVIEW` — 0.30 ≤ score < 0.60 → human review queue
- `ESCALATE` — score ≥ 0.60 → hold order

---

## API Usage

```bash
# Health check
curl https://seyomi-synthguard-api.hf.space/health

# Screen a sequence
curl -X POST https://seyomi-synthguard-api.hf.space/screen \
  -H "Content-Type: application/json" \
  -d '{"sequence": "ATGGCTAGCATG..."}'

# Screen a protein (amino acid sequence)
curl -X POST https://seyomi-synthguard-api.hf.space/protein/screen \
  -H "Content-Type: application/json" \
  -d '{"sequence": "MKCILFLMGTCAVLFLM..."}'

# BioLens integration — DNA
curl -X POST https://seyomi-synthguard-api.hf.space/biolens/screen \
  -H "Content-Type: application/json" \
  -d '{"sequence": "ATGGCTAGCATG...", "seq_type": "DNA"}'

# BioLens integration — protein
curl -X POST https://seyomi-synthguard-api.hf.space/biolens/screen \
  -H "Content-Type: application/json" \
  -d '{"sequence": "MKCILFLMGTCAV...", "seq_type": "PROTEIN"}'

# Track 4: split-order detection
curl -X POST https://seyomi-synthguard-api.hf.space/split/submit \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "cust-001", "order_id": "ord-001", "sequence": "ATGGCTAGC..."}'
```

---

## Quickstart (Colab)

```python
# Train from scratch (GPU recommended)
!git clone https://github.com/Ashok-kumar290/synthscreen
%cd synthscreen
!pip install lightgbm scikit-learn biopython datasets huggingface_hub

# Build dataset (fetches from NCBI, ~20 min)
# See notebooks/synthguard_full.ipynb

# Run full benchmark pipeline
!python scripts/run_pipeline.py \
    --dataset data/processed/synthscreen_dna_v4_dataset \
    --output  results/pipeline \
    --skip_protein --skip_dna --skip_blast
```

---

## Repository Structure

```
synthscreen/
├── app/
│   ├── api.py                    # FastAPI app — all endpoints including Track 4
│   ├── api_space/
│   │   ├── Dockerfile            # HF Space deployment
│   │   └── requirements.txt
│   └── split_order_detector.py   # Track 4 module (standalone reference)
├── scripts/
│   └── run_pipeline.py           # Full benchmark pipeline
├── report/
│   └── hackathon_report.md       # Full technical report
└── data/
    └── processed/                # Built datasets (not committed, on HF Hub)
```

---

## Honest Limitations

- **Protein FPR**: protein k-mer model FPR is 12.5% (vs 6.8% for DNA track). Designed as a confirmation layer, not primary triage.
- **Brucella abortus**: 60.9% recall — virulence factors share k-mer patterns with environmental alpha-proteobacteria; insufficient targeted sequences available from NCBI without access to curated biosecurity DBs
- **Short sequences <150bp**: 14.5% FPR — inherently ambiguous regime; tradeoff between FPR and recall cannot be resolved without wet-lab ground truth
- **BLAST comparison caveat**: our benchmark uses training sequences as the BLAST DB (honest worst-case scenario). Production BLAST with curated, deduplicated DBs would have lower FPR — but the directional conclusion holds
- **No wet-lab validation**: all results are computational

---

## Related Work

- [SecureDNA](https://securedna.org/) — cryptographic DNA screening
- [commec (IBBIS)](https://github.com/ibbis-screening/common-mechanism) — HMM biorisk screening
- [ProteinMPNN](https://github.com/dauparas/ProteinMPNN) — protein sequence design
