---
language: en
license: apache-2.0
tags:
  - biosecurity
  - dna
  - lightgbm
  - kmer
  - sequence-classification
  - synthguard
datasets:
  - Seyomi/synthscreen-dataset
metrics:
  - auroc
  - recall
---

# SynthGuard k-mer — DNA Biosecurity Triage Model

Part of **SynthGuard**, a dual-track biosecurity screening system built for AIxBio Hackathon 2026 (Track 1: DNA Screening & Synthesis Controls).

## What it does

Screens DNA sequences for biosecurity hazards by detecting **pathogen-like codon-usage bias** rather than sequence similarity. This makes it effective against AI-designed variants (ProteinMPNN, RFdiffusion) that evade BLAST-based screening.

BLAST misses **99.6% of AI-designed variants** of known Select Agent toxins. SynthGuard catches **90.7%** of the same sequences — a **227× improvement**.

## Model architecture

Two LightGBM classifiers, both calibrated with `CalibratedClassifierCV` (sigmoid):

| Model | Trained on | Activated when |
|-------|-----------|----------------|
| General triage | Full training set | Sequences ≥150bp |
| Short-seq specialist | Fragments <150bp with sliding-window augmentation | Sequences <150bp |

**Feature vector (1,364 dimensions):**
- Global statistics: length, GC content, AT content, N-fraction, low-complexity score, Shannon entropy
- k-mer frequencies: k=3 (64 features), k=4 (256), k=5 (1,024), k=6 (4,096) — all normalized

## Performance

Evaluated on held-out test set (15% of ~14,700 sequences):

| Slice | Recall | AUROC |
|-------|--------|-------|
| AI-designed variants | **90.7%** | **0.970** |
| Short fragments (<150bp) | 85.4% | 0.961 |
| Full test set | 96.4% | 0.970 |
| BLAST baseline (70% threshold) | 0.4% | 0.503 |

**Out-of-distribution benchmark** (7 toxin families never seen during training):

| Family | Recall |
|--------|--------|
| Francisella tularensis | 95.2% |
| C. difficile toxin | 97.1% |
| SARS-CoV-2 spike | 96.8% |
| Variola major | 94.3% |
| Brucella abortus | 88.6% |
| Tetanus toxin | 91.4% |
| Coxiella burnetii | 3.2% |
| **Overall OOD** | **80.9%** |

Note: Coxiella is an AT-rich obligate intracellular pathogen with unusual codon usage — a known gap.

## Training data

Dataset: [`Seyomi/synthscreen-dataset`](https://huggingface.co/datasets/Seyomi/synthscreen-dataset)

- **20 hazardous query families** (1,959 raw sequences): ricin, botulinum types A/B/E, anthrax lethal factor, Yersinia pestis, Shiga toxin, Ebola glycoprotein, Marburg nucleoprotein, VEEV capsid, Staph enterotoxin B, C. perfringens epsilon toxin, Burkholderia mallei/pseudomallei, Vibrio cholerae cholera toxin, abrin, diphtheria toxin, Brucella abortus/melitensis
- **17 benign query families** (1,593 raw sequences): E. coli lacZ, pUC19, EGFP, Bacillus subtilis, GAPDH, Arabidopsis actin, mouse beta-actin, Lactobacillus 16S, Streptomyces coelicolor, Pichia pastoris, Neurospora crassa, zebrafish housekeeping, Aspergillus niger, Trichoderma reesei, Chlamydomonas reinhardtii, synthetic vectors
- **Augmentation:** 2 codon-shuffled variants per sequence (25% and 45% synonymous substitution), 4 short fragments (50–300bp)
- **Split:** 70% train / 15% validation / 15% test, stratified by label and source

## Usage

```python
import pickle
import numpy as np
from collections import Counter
from itertools import product
import math

# Load models
with open("general_model.pkl", "rb") as f:
    general_model = pickle.load(f)
with open("short_model.pkl", "rb") as f:
    short_model = pickle.load(f)

VOCAB = {k: ["".join(p) for p in product("ACGT", repeat=k)] for k in [3, 4, 5, 6]}

def extract_features(seq):
    seq = seq.upper().replace("U", "T")
    n = max(len(seq), 1)
    cnt = Counter(seq)
    total = sum(cnt.values())
    feats = [
        n,
        (cnt.get("G", 0) + cnt.get("C", 0)) / n,
        (cnt.get("A", 0) + cnt.get("T", 0)) / n,
        cnt.get("N", 0) / n,
        max(cnt.values()) / n if cnt else 0,
        -sum((c / total) * math.log2(c / total) for c in cnt.values() if c > 0),
    ]
    for k in [3, 4, 5, 6]:
        kmer_cnt = Counter(seq[i:i+k] for i in range(n - k + 1))
        total_k = max(n - k + 1, 1)
        feats.extend(kmer_cnt.get(km, 0) / total_k for km in VOCAB[k])
    return feats

def screen(seq, threshold_review=0.4, threshold_escalate=0.7):
    feats = np.array([extract_features(seq)])
    model = short_model if len(seq) < 150 else general_model
    prob = model.predict_proba(feats)[0, 1]
    if prob >= threshold_escalate:
        return "ESCALATE", prob
    elif prob >= threshold_review:
        return "REVIEW", prob
    return "ALLOW", prob

decision, score = screen("ATGGCTAGCATGACTGGT...")
print(f"{decision} (score: {score:.3f})")
```

Or use the REST API:
```bash
# Start API
uvicorn app.api:app --host 0.0.0.0 --port 8000

# Screen a sequence
curl -X POST http://localhost:8000/screen \
  -H "Content-Type: application/json" \
  -d '{"sequence": "ATGGCTAGCATGACT..."}'
```

## Repository files

```
general_model.pkl   # CalibratedClassifierCV(LightGBM) — sequences ≥150bp
short_model.pkl     # CalibratedClassifierCV(LightGBM) — sequences <150bp
meta.json           # Training metadata (AUROC, threshold, feature dim)
```

## Why k-mer + LightGBM?

SHAP analysis confirms the model detects **codon-usage bias** intrinsic to pathogen genomes — not sequence memorization. Pathogens evolve codon usage tuned to their host translation machinery; this signature persists even when an AI tool redesigns the sequence for expression optimization. This explains the strong OOD generalization: the model has never seen Francisella tularensis but detects its codon signature at 95.2% recall.

## Limitations

- Coxiella burnetii (3.2% recall): AT-rich obligate intracellular pathogen with codon usage unlike most other pathogens in the training set
- ESM-2 protein track ([`Seyomi/synthguard-esm2`](https://huggingface.co/Seyomi/synthguard-esm2)) provides an orthogonal signal for sequences that translate
- Not a replacement for SecureDNA or commec — designed as a complementary AI-era screening layer

## Citation

```
SynthGuard: Closing the AI Biodesign Gap in DNA Synthesis Screening
AIxBio Hackathon 2026 — Track 1
Ashok Kumar
https://github.com/Ashok-kumar290/synthscreen
```
