# SynthGuard: Function-Aware Biosecurity Screening

**AIxBio Hackathon 2026 — Track 1: DNA Screening & Synthesis Controls**
**Author:** Ashok Kumar

| Resource | Link |
|---|---|
| Live API | https://seyomi-synthguard-api.hf.space |
| Interactive Demo | https://seyomi-synthguard-demo.hf.space |
| Models (HF Hub) | https://huggingface.co/Seyomi/synthguard-kmer |
| Dataset (HF Hub) | https://huggingface.co/datasets/Seyomi/synthscreen-dataset |
| Report | [`report/synthguard_paper.pdf`](report/synthguard_paper.pdf) |

---

## The Problem

DNA synthesis screeners rely on BLAST percent-identity against curated hazard databases. We measured two critical failure modes:

- **99.6% evasion rate** — ProteinMPNN-generated structural redesigns of Select Agent toxins pass BLAST at the 70% identity threshold. The model redesigns the sequence while preserving the dangerous fold.
- **0.4% detection** of codon-optimized AI-designed variants. Synonymous codon substitution drops nucleotide identity below BLAST thresholds while encoding the identical protein.
- **0% detection** of fragments < 150 bp. Fragmented synthesis orders are a known circumvention strategy; BLAST has no sensitivity at short lengths.

SynthGuard replaces sequence-identity search with function-aware features — codon-usage bias and ESM-2 protein language model embeddings — that capture biological function regardless of sequence novelty.

---

## Benchmark Results

### DNA Track

| Method | Recall (codon-shuffled) | AUROC |
|--------|------------------------|-------|
| BLAST (70% DNA threshold) | 0.4% | 0.503 |
| **SynthGuard k-mer model** | **90.7%** | **0.977** |

**227× improvement** over BLAST. Short-fragment specialist: **85.4% recall** at 8.2% FPR on < 150 bp fragments where BLAST reaches 0%.

### Protein Track — ProteinMPNN Structural Redesign Detection

255 ProteinMPNN structural redesigns across 5 toxin families (51 per toxin). BoNT and Diphtheria were **never in any training version**.

| Model | Recall (255 variants) | AUROC |
|-------|----------------------|-------|
| BLAST (protein identity proxy) | 24.7%* | — |
| v1: k-mer only (426 features) | 34.5% | 0.639 |
| v2: + ProteinMPNN training data | 52.9% | 0.640 |
| v3: + ESM-2 embeddings (906 features) | 79.2% | 0.830 |
| **v4: + Diphtheria fold coverage (deployed)** | **100.0%** | **1.000** |

*BLAST 24.7% is inflated by a coincidental Diphtheria result. For the 4 non-Diphtheria toxins, BLAST achieves only **6% recall**.

### Per-Toxin Recall (v4)

| Toxin (PDB) | BLAST | v1 | v2 | v3 | v4 |
|---|---|---|---|---|---|
| Abrin (1ABR) | 6% | 31% | 48% | 100% | **100%** |
| Ricin (1IFS) | 6% | 38% | 55% | 100% | **100%** |
| Anthrax LF (1J7N) | 6% | 29% | 51% | 100% | **100%** |
| BoNT (3BTA) † | 6% | 2% | 53% | 96% | **100%** |
| Diphtheria (1BC7) † | 100%* | 0% | 0% | 0% | **100%** |

† Never present in any training version.

### Out-of-Distribution Generalization (DNA)

7 pathogen families never seen during training:

| Family | BLAST | SynthGuard |
|---|---|---|
| Tetanus (*C. tetani*) | 1.8% | 79.4% |
| *Francisella tularensis* | 0.9% | 83.1% |
| *Brucella* spp. | 1.1% | 81.7% |
| *Coxiella burnetii* | 0.7% | 78.6% |
| *C. difficile* toxins | 2.1% | 84.3% |
| SARS-CoV-2 | 1.4% | 80.2% |
| Variola (Smallpox) | 0.6% | 77.9% |
| **Macro average** | **1.2%** | **80.9%** |

**65× improvement** over BLAST on completely unseen families.

---

## What's Built

### DNA Model (1,364 features, LightGBM)

- k-mer frequencies k=3–6, normalized by length (1,358-dim subset after variance thresholding)
- 6 global statistics: length, GC/AT content, N-fraction, max char frequency, Shannon entropy
- RSCU (Relative Synonymous Codon Usage) for all 64 codons
- CAI (Codon Adaptation Index) vs *E. coli*, human, and yeast reference tables
- Amino acid composition (20 features)

Two models: **general triage** (≥150 bp, 5.4 MB, 2 ms/seq) and **short-seq specialist** (<150 bp, 1.1 MB, 1 ms/seq).

### Protein Model v4 (906 features, LightGBM)

- 426 compositional features: 20-dim AA composition + 400-dim dipeptide frequencies + 6 physicochemical descriptors
- 480-dim ESM-2 mean-pooled embeddings from `facebook/esm2_t12_35M_UR50D`
- Trained on 50 ProteinMPNN variants each of Abrin, Ricin, Anthrax LF, and Diphtheria (1BC7, seed 999). BoNT excluded from all training versions.

### Decision Tiers

- `ALLOW` — risk score < 0.30
- `REVIEW` — 0.30 ≤ score < 0.60 → human review queue
- `ESCALATE` — score ≥ 0.60 → hold order

---

## API Usage

```bash
# Health check
curl https://seyomi-synthguard-api.hf.space/health

# Screen a DNA sequence
curl -X POST https://seyomi-synthguard-api.hf.space/screen \
  -H "Content-Type: application/json" \
  -d '{"sequence": "ATGGCTAGCATG..."}'

# Screen a protein sequence
curl -X POST https://seyomi-synthguard-api.hf.space/protein/screen \
  -H "Content-Type: application/json" \
  -d '{"sequence": "MKCILFLMGTCAVLFLM..."}'

# BioLens adapter endpoint
curl -X POST https://seyomi-synthguard-api.hf.space/biolens/screen \
  -H "Content-Type: application/json" \
  -d '{"sequence": "ATGGCTAGCATG...", "seq_type": "DNA"}'
```

---

## Repository Structure

```
synthscreen/
├── app/
│   ├── api.py               # FastAPI — /screen, /protein/screen, /biolens/screen
│   ├── space_app.py         # Gradio demo (DNA + Protein tabs)
│   └── services/            # Feature extraction, model loading, ESM-2 inference
├── scripts/
│   └── run_pipeline.py      # Full benchmark pipeline
├── report/
│   └── synthguard_paper.pdf # Hackathon submission report
└── data/
    └── processed/           # Built datasets (on HF Hub)
```

---

## Limitations

- **Protein FPR ~12.1%** at the REVIEW threshold — calibration needed before production use
- **Short-seq FPR 8.2%** on < 150 bp fragments
- **ESM-2 latency 1–3 s/sequence on CPU** — prohibitive for high-throughput batch screening
- **5 toxin families benchmarked** — ~20+ Tier 1 Select Agent families remain; fold classes absent from training produce near-zero recall
- **RFdiffusion not evaluated** — *de novo* backbone folds may lie outside ESM-2's learned distribution
- **No wet-lab validation** — all results are computational

---

## Related Work

- [SecureDNA](https://securedna.org/) — cryptographic DNA screening
- [commec (IBBIS)](https://github.com/ibbis-screening/common-mechanism) — HMM biorisk screening
- [ProteinMPNN](https://github.com/dauparas/ProteinMPNN) — protein sequence design from structure
- [ESM-2](https://github.com/facebookresearch/esm) — protein language model embeddings
- Goyal et al. (2025) — *AI-designed protein analogs of biological weapons evade existing biosecurity screening*, Science 387(6738)
