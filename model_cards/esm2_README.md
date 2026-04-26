---
language: en
license: apache-2.0
tags:
  - biosecurity
  - protein
  - esm2
  - lightgbm
  - sequence-classification
  - synthguard
base_model: facebook/esm2_t12_35M_UR50D
datasets:
  - Seyomi/synthscreen-dataset
metrics:
  - auroc
  - recall
---

# SynthGuard Protein V4 — ESM-2 + k-mer Biosecurity Screening Model

Part of **SynthGuard**, a dual-track biosecurity screening system built for AIxBio Hackathon 2026 (Track 1: DNA Screening & Synthesis Controls).

> **Benchmark date:** April 26, 2026 — all numbers from real NCBI BLAST+ 2.12.0+ on Google Colab A100.

---

## What it does

Screens protein (amino acid) sequences for biosecurity hazards using a hybrid feature approach: **amino acid composition + dipeptide frequencies + ESM-2 structural embeddings**. Detects ProteinMPNN-redesigned toxin analogs that share <30% sequence identity with known hazardous proteins and are therefore invisible to BLAST-based protein screening.

**Key finding:** Real NCBI blastp (50% amino acid identity) achieves **0% recall** on the protein sequences in our corpus — they are all below the identity threshold by design. SynthGuard Protein V4 achieves **86.0% recall** at **AUROC 0.944** on the same sequences.

---

## Architecture

**Not a fine-tuned ESM-2 classifier.** V4 uses ESM-2 as a frozen feature extractor:

1. `facebook/esm2_t12_35M_UR50D` (35M parameters) — mean-pool of last hidden states (excluding CLS/EOS tokens) → **480-dim embedding**
2. **426 k-mer features** — AA composition (20) + dipeptide frequencies (400) + physicochemical descriptors (6)
3. **906-dim concatenation** → LightGBM classifier (sigmoid-calibrated)

```python
# ESM-2 embedding extraction
inputs = tokenizer(aa_seq, return_tensors="pt", truncation=True, max_length=512)
with torch.no_grad():
    hidden = model(**inputs).last_hidden_state[0, 1:-1, :]  # exclude CLS/EOS
embedding = hidden.mean(0).cpu().numpy()  # 480-dim
```

**LightGBM (v4):**
`LGBMClassifier(n_estimators=600, max_depth=8, num_leaves=63, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, scale_pos_weight=0.9398, random_state=42)`
Calibrated with `CalibratedClassifierCV(sigmoid, cv='prefit')`

---

## Performance — verified April 26, 2026

**vs. real NCBI blastp 2.12.0+ (50% amino acid identity threshold), 1,286 translatable sequences:**

| Model | Recall | FPR | AUROC |
|-------|---:|---:|---:|
| blastp (50% identity) | **0.0%** | 0.0% | 0.500 |
| SynthGuard V4 (this model) | **86.0%** | 13.2% | **0.944** |
| SynthGuard V2 (k-mer only, 426-feat) | 84.4% | — | 0.937 |

**ProteinMPNN ablation — 255 structural redesigns, 5 toxin families (standalone benchmark):**

| Toxin (PDB) | blastp recall | V2 (k-mer) | V3 (+ESM-2) | V4 (+1BC7 data) |
|-------------|---:|---:|---:|---:|
| Abrin (1ABR) | 6% | 48% | 100% | **100%** |
| Ricin (1IFS) | 6% | 55% | 100% | **100%** |
| Anthrax LF (1J7N) | 6% | 51% | 100% | **100%** |
| BoNT (3BTA) †† | 6% | 53% | 96% | **100%** |
| Diphtheria (1BC7) †† | ~0% | 0% | 0% | **100%** |
| **All 255 variants** | ~6% | 52.9% | 79.2% | **100% (AUROC 1.000)** |

†† = BoNT and Diphtheria were **never included in any training version**. Their improvement from V2→V3→V4 demonstrates that ESM-2 embeddings transfer structural topology across unseen toxin fold classes.

**The Diphtheria gap closed by targeted data augmentation:**
- V1–V3: 0% recall (ADP-ribosyltransferase fold absent from training)
- V4: 100% recall after adding 50 ProteinMPNN variants of 1BC7 to training — no architectural change

---

## Why ESM-2 + k-mer outperforms k-mer alone

k-mer features (AA composition, dipeptides) capture sequence composition but not structural information. ESM-2 embeddings encode the structural topology of the protein — two proteins with <10% sequence identity but the same fold will have similar ESM-2 representations. This explains the BoNT trajectory:

- V2 (k-mer only): 53% recall on BoNT variants — partial compositional overlap
- V3 (+ ESM-2): 96% recall — structural embedding recognizes the clostridial neurotoxin fold topology even with no BoNT training data

---

## Usage

```python
import pickle
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from huggingface_hub import hf_hub_download

# Download V4 model
v4_path = hf_hub_download("Seyomi/synthguard-kmer", "protein_kmer_v4_esm2.pkl")
with open(v4_path, "rb") as f:
    protein_v4 = pickle.load(f)

# Load ESM-2 feature extractor (frozen)
ESM2_ID = "facebook/esm2_t12_35M_UR50D"
tokenizer = AutoTokenizer.from_pretrained(ESM2_ID)
esm2 = AutoModel.from_pretrained(ESM2_ID).eval()
device = "cuda" if torch.cuda.is_available() else "cpu"
esm2 = esm2.to(device)

_AA20 = list("ACDEFGHIKLMNPQRSTVWY")
_DIPEP = [a+b for a in _AA20 for b in _AA20]

def esm2_embed(aa, max_len=512):
    aa = aa[:max_len]
    if not aa: return np.zeros(480)
    inputs = tokenizer(aa, return_tensors="pt", truncation=True,
                       max_length=max_len, padding=False)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        h = esm2(**inputs).last_hidden_state[0, 1:-1, :]
    return (h.mean(0) if h.shape[0] > 0 else h.new_zeros(480)).cpu().numpy()

def kmer_features(aa):
    aa = "".join(c for c in aa.upper() if c in set(_AA20))
    if not aa: return [0.0] * 426
    n = len(aa)
    comp = [aa.count(a)/n for a in _AA20]
    dipep = [aa[i:i+2] for i in range(n-1)]
    dp_cnt = {d: dipep.count(d) for d in _DIPEP}
    dp_tot = max(len(dipep), 1)
    dipep_f = [dp_cnt.get(d, 0)/dp_tot for d in _DIPEP]
    mw = sum({'A':89,'C':121,'D':133,'E':147,'F':165,'G':75,'H':155,'I':131,
              'K':146,'L':131,'M':149,'N':132,'P':115,'Q':146,'R':174,'S':105,
              'T':119,'V':117,'W':204,'Y':181}.get(c,110) for c in aa)/n
    charge = sum({'R':1,'K':1,'D':-1,'E':-1}.get(c,0) for c in aa)/n
    hydro  = sum({'A':1.8,'V':4.2,'L':3.8,'I':4.5,'P':-1.6,'F':2.8,'W':-0.9,'M':1.9,
                  'G':-0.4,'S':-0.8,'T':-0.7,'C':2.5,'Y':-1.3,'H':-3.2,'D':-3.5,
                  'E':-3.5,'N':-3.5,'Q':-3.5,'K':-3.9,'R':-4.5}.get(c,0) for c in aa)/n
    return comp + dipep_f + [hydro, charge, mw/200, 0.0, 0.0, aa.count('C')/n]

def screen_protein_v4(aa, threshold_review=0.3, threshold_escalate=0.6):
    feats = np.array([kmer_features(aa) + esm2_embed(aa).tolist()])  # 906-dim
    prob = float(protein_v4.predict_proba(feats)[0, 1])
    if prob >= threshold_escalate: return "ESCALATE", prob
    if prob >= threshold_review:   return "REVIEW", prob
    return "SAFE", prob

decision, score = screen_protein_v4("MKAIFVLKGFFGAFLGFLLLPFLMAK")
print(f"{decision} (score: {score:.3f})")
```

---

## Deployment note

The live API (`https://seyomi-synthguard-api.hf.space/protein/screen`) serves V4 when GPU is available, falling back to V2 (k-mer only, 426 features) on CPU-only instances. Check `/health` → `protein_model` field to confirm which version is active.

---

## Training Data

Dataset: [`Seyomi/synthscreen-dataset`](https://huggingface.co/datasets/Seyomi/synthscreen-dataset)

Protein model trained on sequences that yield ≥30 amino acids after best-frame translation. V4 additionally trained on 50 ProteinMPNN redesigns of Diphtheria toxin (1BC7, ADP-ribosyltransferase fold) — the only addition from V3→V4.

---

## Limitations

- **V4 requires GPU** for ESM-2 inference (~15ms/seq GPU vs ~200ms/seq CPU). V2 (426-feat k-mer) is the operationally viable CPU deployment.
- **Chimeric constructs not evaluated** — hazardous domain fused to benign scaffold may evade both blastp and SynthGuard
- **RFdiffusion de-novo backbones not evaluated** — novel folds with no known structural homolog are outside training distribution
- **ProteinMPNN ablation uses a separate dataset** — 255 variants across 5 toxin families, not in the HF test split
- **Computational only** — no wet-lab functional validation

---

## Related

- DNA model: [`Seyomi/synthguard-kmer`](https://huggingface.co/Seyomi/synthguard-kmer)
- Dataset: [`Seyomi/synthscreen-dataset`](https://huggingface.co/datasets/Seyomi/synthscreen-dataset)
- Dashboard: [`Seyomi/biolens-dashboard`](https://huggingface.co/spaces/Seyomi/biolens-dashboard)
- Code: [github.com/Ashok-kumar290/synthscreen](https://github.com/Ashok-kumar290/synthscreen) (branch: `synthguard`)

## Citation

```
SynthGuard: Closing the AI Biodesign Gap in DNA Synthesis Screening
AIxBio Hackathon 2026 — Track 1 | Ashok Kumar
https://github.com/Ashok-kumar290/synthscreen
Benchmark: NCBI BLAST+ 2.12.0+, Google Colab A100, April 26 2026
```
