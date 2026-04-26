---
language: en
license: apache-2.0
tags:
  - biosecurity
  - dna
  - protein
  - lightgbm
  - kmer
  - sequence-classification
  - synthguard
  - codon-usage
datasets:
  - Seyomi/synthscreen-dataset
metrics:
  - auroc
  - recall
---

# SynthGuard k-mer — DNA & Protein Biosecurity Screening Models

Part of **SynthGuard**, a dual-track biosecurity screening system built for AIxBio Hackathon 2026 (Track 1: DNA Screening & Synthesis Controls).

> **Benchmark date:** April 26, 2026 — all numbers from real NCBI BLAST+ 2.12.0+ on Google Colab A100.

---

## What it does

Screens DNA and protein sequences for biosecurity hazards by detecting **pathogen-associated codon-usage bias** rather than requiring sequence identity to known threats. This makes it effective against AI-designed variants (ProteinMPNN, codon optimization) that evade standard BLAST-based screening.

**Key finding:** Real NCBI blastn (70% identity) achieves AUROC **0.526** — statistically equivalent to random discrimination. SynthGuard achieves AUROC **0.968** on the same sequences. blastn flags 94.3% of benign sequences as hazardous; SynthGuard flags only 8.0%.

---

## Models in this repository

| File | Description | Features | Use when |
|------|-------------|----------|----------|
| `general_model.pkl` | DNA general triage | 5,533 | Sequences ≥150 bp |
| `short_model.pkl` | DNA short-seq specialist | 5,533 | Sequences <150 bp |
| `protein_kmer_model.pkl` | Protein k-mer classifier (v2) | 426 | Protein/AA sequences, CPU inference |
| `protein_kmer_v4_esm2.pkl` | Protein ESM-2 + k-mer (v4) | 906 | Protein/AA sequences, GPU available |
| `meta.json` | Feature names, thresholds, version | — | Feature extraction reference |

---

## DNA Model

### Architecture

Two LightGBM classifiers, both calibrated with `CalibratedClassifierCV(sigmoid, cv='prefit')`:

**General triage (≥150 bp):**
`LGBMClassifier(n_estimators=500, max_depth=7, num_leaves=63, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, class_weight='balanced', random_state=42)`

**Short-seq specialist (<150 bp):**
`LGBMClassifier(n_estimators=400, max_depth=5, num_leaves=31, learning_rate=0.05, subsample=0.8, colsample_bytree=0.7, class_weight='balanced', random_state=42)`

### Feature vector — 5,533 dimensions

| Group | Features | Count |
|-------|----------|------:|
| Global statistics | Length, GC%, AT%, N-fraction, max-char freq, Shannon entropy | 6 |
| k-mer frequencies | All k-mers k∈{3,4,5,6}, normalized by sequence length | 5,440 |
| RSCU | Relative synonymous codon usage, all 64 codons | 64 |
| CAI | Codon adaptation index vs. E. coli, human, yeast (Kazusa) | 3 |
| AA composition | Amino acid frequency in best reading frame (20 AAs) | 20 |
| **Total** | | **5,533** |

Feature version: `v2_codon_norm` (see `meta.json`)

### Why codon bias?

Codon-usage bias is an organism-of-origin fingerprint. A codon-optimized pathogen gene exhibits high human-host CAI and biased RSCU toward human-preferred codons. This signal is **invisible to nucleotide identity search** — it persists through synonymous substitution — yet is characteristic of sequences prepared for expression in a target host.

### DNA Performance — verified April 26, 2026

**vs. real NCBI blastn 2.12.0+ (70% identity threshold):**

| Slice | n | blastn Recall | blastn FPR | blastn AUROC | SynthGuard Recall | SynthGuard FPR | SynthGuard AUROC |
|-------|---|---:|---:|---:|---:|---:|---:|
| Full test set | 2,214 | 99.4% | 94.3% | 0.526 | **88.5%** | **8.0%** | **0.968** |
| Original sequences | 532 | 98.7% | 97.4% | 0.507 | **96.1%** | **1.1%** | **0.989** |
| Fragments <150 bp | 555 | 99.6% | 98.7% | 0.504 | **76.3%** | **16.6%** | **0.878** |
| AI-generated (codon-shuffled) | 1,682 | 99.6% | 92.8% | 0.534 | **87.2%** | **11.3%** | **0.954** |

blastn AUROC ≈ 0.526 means no threshold choice makes it a useful discriminator. SynthGuard AUROC 0.968 enables operators to set thresholds appropriate to their risk tolerance.

### OOD Generalization — 7 unseen toxin families

Verified April 26, 2026 (`notebooks/ood_blastn_benchmark.py`, real blastn 2.12.0+, 1,600 sequences):

| Slice | blastn AUROC | SynthGuard AUROC | SynthGuard Recall | SynthGuard FPR |
|-------|---:|---:|---:|---:|
| Full OOD set | 0.514 | **0.958** | 91.6% | 12.2% |
| Original sequences | 0.510 | **0.986** | 98.9% | 4.8% |
| Codon-shuffled variants | 0.520 | **0.924** | 88.0% | 19.8% |

**Per-family recall (original sequences, no retraining):**

| Family | SynthGuard | blastn | n |
|--------|---:|---:|---|
| Tetanus toxin (*C. tetani*) | **100%** | 100% | 11 |
| *Francisella tularensis* | **100%** | 100% | 23 |
| *Brucella abortus* | **85%** | 100% | 20 |
| *Coxiella burnetii* | **100%** | 100% | 30 |
| *C. difficile* toxin A | **100%** | 100% | 39 |
| SARS-CoV-2 spike | **100%** | 100% | 72 |
| Variola virus | **100%** | 100% | 70 |

*Brucella abortus* (85%) is the only gap — its obligate-intracellular high-GC codon usage diverges from the training distribution. All other OOD families: 100% recall.

### DNA Usage

```python
import pickle, math, numpy as np
from collections import Counter
from itertools import product

# Download from HuggingFace
from huggingface_hub import hf_hub_download
general_path = hf_hub_download("Seyomi/synthguard-kmer", "general_model.pkl")
short_path   = hf_hub_download("Seyomi/synthguard-kmer", "short_model.pkl")

with open(general_path, "rb") as f: general_model = pickle.load(f)
with open(short_path,   "rb") as f: short_model   = pickle.load(f)

# ── Feature extractor (5,533 features — must match exactly) ──────────────────
CODON_TABLE = {
    'TTT':'F','TTC':'F','TTA':'L','TTG':'L','CTT':'L','CTC':'L','CTA':'L','CTG':'L',
    'ATT':'I','ATC':'I','ATA':'I','ATG':'M','GTT':'V','GTC':'V','GTA':'V','GTG':'V',
    'TCT':'S','TCC':'S','TCA':'S','TCG':'S','CCT':'P','CCC':'P','CCA':'P','CCG':'P',
    'ACT':'T','ACC':'T','ACA':'T','ACG':'T','GCT':'A','GCC':'A','GCA':'A','GCG':'A',
    'TAT':'Y','TAC':'Y','TAA':'*','TAG':'*','CAT':'H','CAC':'H','CAA':'Q','CAG':'Q',
    'AAT':'N','AAC':'N','AAA':'K','AAG':'K','GAT':'D','GAC':'D','GAA':'E','GAG':'E',
    'TGT':'C','TGC':'C','TGA':'*','TGG':'W','CGT':'R','CGC':'R','CGA':'R','CGG':'R',
    'AGT':'S','AGC':'S','AGA':'R','AGG':'R','GGT':'G','GGC':'G','GGA':'G','GGG':'G',
}
_AA_CODONS = {}
for c, a in CODON_TABLE.items(): _AA_CODONS.setdefault(a, []).append(c)
ALL_CODONS  = sorted(CODON_TABLE.keys())
AMINO_ACIDS = sorted(a for a in set(CODON_TABLE.values()) if a != '*')
VOCAB = {k: ["".join(p) for p in product("ACGT", repeat=k)] for k in [3,4,5,6]}

# Kazusa DB (E. coli / human / yeast) for CAI
_ECOLI = {'TTT':22.0,'TTC':16.5,'TTA':13.9,'TTG':13.1,'CTT':10.9,'CTC':10.0,'CTA':3.8,'CTG':52.7,'ATT':28.8,'ATC':25.1,'ATA':4.4,'ATG':27.4,'GTT':19.5,'GTC':14.7,'GTA':10.8,'GTG':25.9,'TCT':7.8,'TCC':8.8,'TCA':7.0,'TCG':8.7,'CCT':7.2,'CCC':5.6,'CCA':8.4,'CCG':23.3,'ACT':9.0,'ACC':23.4,'ACA':7.2,'ACG':14.6,'GCT':15.3,'GCC':25.8,'GCA':20.6,'GCG':33.5,'TAT':16.3,'TAC':12.5,'TAA':2.0,'TAG':0.3,'CAT':13.2,'CAC':9.6,'CAA':15.5,'CAG':28.7,'AAT':22.3,'AAC':22.4,'AAA':33.6,'AAG':10.1,'GAT':32.2,'GAC':19.0,'GAA':39.8,'GAG':18.3,'TGT':5.0,'TGC':6.5,'TGA':1.0,'TGG':15.2,'CGT':21.1,'CGC':21.7,'CGA':3.7,'CGG':5.3,'AGT':8.7,'AGC':15.8,'AGA':3.5,'AGG':2.9,'GGT':24.7,'GGC':29.5,'GGA':8.0,'GGG':11.5}
_HUMAN  = {'TTT':17.6,'TTC':20.3,'TTA':7.7,'TTG':12.9,'CTT':13.2,'CTC':19.6,'CTA':7.2,'CTG':39.6,'ATT':16.0,'ATC':20.8,'ATA':7.5,'ATG':22.0,'GTT':11.0,'GTC':14.5,'GTA':7.1,'GTG':28.1,'TCT':15.2,'TCC':17.7,'TCA':12.2,'TCG':4.4,'CCT':17.5,'CCC':19.8,'CCA':16.9,'CCG':6.9,'ACT':13.1,'ACC':18.9,'ACA':15.1,'ACG':6.1,'GCT':18.4,'GCC':27.7,'GCA':15.8,'GCG':7.4,'TAT':12.2,'TAC':15.3,'TAA':1.0,'TAG':0.8,'CAT':10.9,'CAC':15.1,'CAA':12.3,'CAG':34.2,'AAT':17.0,'AAC':19.1,'AAA':24.4,'AAG':31.9,'GAT':21.8,'GAC':25.1,'GAA':29.0,'GAG':39.6,'TGT':10.6,'TGC':12.6,'TGA':1.6,'TGG':13.2,'CGT':4.5,'CGC':10.4,'CGA':6.2,'CGG':11.4,'AGT':15.2,'AGC':19.5,'AGA':11.5,'AGG':11.4,'GGT':10.8,'GGC':22.2,'GGA':16.5,'GGG':16.5}
_YEAST  = {'TTT':26.2,'TTC':18.4,'TTA':26.2,'TTG':27.2,'CTT':12.3,'CTC':5.4,'CTA':13.4,'CTG':10.5,'ATT':30.1,'ATC':17.2,'ATA':17.8,'ATG':20.9,'GTT':22.1,'GTC':11.8,'GTA':11.8,'GTG':10.8,'TCT':23.5,'TCC':14.2,'TCA':18.7,'TCG':8.6,'CCT':13.5,'CCC':6.8,'CCA':18.3,'CCG':5.4,'ACT':20.3,'ACC':13.1,'ACA':17.9,'ACG':8.1,'GCT':21.1,'GCC':12.6,'GCA':16.0,'GCG':6.2,'TAT':18.8,'TAC':14.8,'TAA':1.1,'TAG':0.5,'CAT':13.6,'CAC':7.8,'CAA':27.3,'CAG':12.1,'AAT':35.9,'AAC':24.8,'AAA':41.9,'AAG':30.8,'GAT':37.6,'GAC':20.2,'GAA':45.0,'GAG':19.2,'TGT':8.1,'TGC':4.8,'TGA':0.7,'TGG':10.4,'CGT':6.4,'CGC':2.6,'CGA':3.0,'CGG':1.7,'AGT':14.2,'AGC':9.8,'AGA':21.3,'AGG':9.2,'GGT':23.9,'GGC':9.8,'GGA':10.9,'GGG':6.0}

def _ref_rscu(ft):
    rscu = {}
    for aa, codons in _AA_CODONS.items():
        if aa == '*':
            for c in codons: rscu[c] = 1.0; continue
        mf = max(ft.get(c, 0.1) for c in codons)
        for c in codons: rscu[c] = ft.get(c, 0.1) / mf if mf > 0 else 1.0
    return rscu

_ECOLI_RSCU = _ref_rscu(_ECOLI)
_HUMAN_RSCU = _ref_rscu(_HUMAN)
_YEAST_RSCU = _ref_rscu(_YEAST)

def _codon_features(seq):
    cc = Counter(seq[i:i+3] for i in range(0, len(seq)-2, 3) if seq[i:i+3] in CODON_TABLE)
    rscu = {}
    for aa, codons in _AA_CODONS.items():
        if aa == '*':
            for c in codons: rscu[c] = 1.0; continue
        tot = sum(cc.get(c,0) for c in codons); n = len(codons)
        exp = tot/n if tot > 0 else 0
        for c in codons: rscu[c] = cc.get(c,0)/exp if exp > 0 else 1.0
    rscu_f = [rscu.get(c, 1.0) for c in ALL_CODONS]
    def cai(ref):
        s,n = 0.0,0
        for c,k in cc.items():
            if CODON_TABLE.get(c,'*') != '*': s += math.log(max(ref.get(c,0.01),1e-6))*k; n+=k
        return math.exp(s/n) if n else 0.5
    aa_tot = sum(k for c,k in cc.items() if CODON_TABLE.get(c,'*')!='*')
    aa_cnt = Counter({CODON_TABLE[c]:k for c,k in cc.items() if CODON_TABLE.get(c,'*')!='*'})
    return rscu_f + [cai(_ECOLI_RSCU), cai(_HUMAN_RSCU), cai(_YEAST_RSCU)] + \
           [aa_cnt.get(a,0)/max(aa_tot,1) for a in AMINO_ACIDS]

def extract_features(seq):
    seq = seq.upper().replace("U","T")
    n = max(len(seq),1); cnt = Counter(seq); tot = sum(cnt.values())
    feats = [n, (cnt.get("G",0)+cnt.get("C",0))/n, (cnt.get("A",0)+cnt.get("T",0))/n,
             cnt.get("N",0)/n, max(cnt.values())/n if cnt else 0,
             -sum((c/tot)*math.log2(c/tot) for c in cnt.values() if c>0)]
    for k in [3,4,5,6]:
        kc = Counter(seq[i:i+k] for i in range(n-k+1))
        tk = max(n-k+1,1)
        feats.extend(kc.get(km,0)/tk for km in VOCAB[k])
    feats.extend(_codon_features(seq))
    return feats  # 5,533 features

# ── Inference ─────────────────────────────────────────────────────────────────
def screen_dna(seq, threshold_review=0.3, threshold_escalate=0.6):
    feats = np.array([extract_features(seq)])
    model = short_model if len(seq) < 150 else general_model
    prob = float(model.predict_proba(feats)[0, 1])
    if prob >= threshold_escalate: return "ESCALATE", prob
    if prob >= threshold_review:   return "REVIEW", prob
    return "SAFE", prob

decision, score = screen_dna("ATGGCTAGCATGACTGGTGGACAGCAAATGGG")
print(f"{decision} (score: {score:.3f})")
```

---

## Protein Model

### Architecture

Two versions are available:

**V2 — k-mer only (426 features, deployed API, CPU inference ~2ms):**
`LGBMClassifier(n_estimators=600, max_depth=8, num_leaves=63, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8)`

Features: AA composition (20) + dipeptide frequencies (400) + physicochemical descriptors (6)

**V4 — ESM-2 + k-mer (906 features, benchmarked model, GPU recommended):**
Same LightGBM, but input = 426 k-mer features + 480-dim ESM-2 mean-pool embeddings from `facebook/esm2_t12_35M_UR50D`

### Protein Performance — verified April 26, 2026

**vs. real NCBI blastp 2.12.0+ (50% amino acid identity threshold):**

| Model | Recall | FPR | AUROC | n |
|-------|---:|---:|---:|---|
| blastp (50% identity) | **0.0%** | 0.0% | 0.500 | 1,286 |
| SynthGuard V4 (906-feat) | **86.0%** | 13.2% | **0.944** | 1,286 |
| SynthGuard V2 API (426-feat) | 84.4% | — | 0.937 | HF test set |

blastp achieves **zero recall** — ProteinMPNN-redesigned and AI-generated protein sequences in our corpus are all below the 50% identity threshold by design. SynthGuard detects them via amino acid composition and dipeptide patterns characteristic of toxin fold families.

**Protein ablation — 255 ProteinMPNN variants (standalone benchmark, separate dataset):**

| Toxin (PDB) | Identity baseline | V1 | V2 | V3 (+ESM-2) | V4 (+1BC7) |
|-------------|---:|---:|---:|---:|---:|
| Abrin (1ABR) | 6% | 31% | 48% | 100% | **100%** |
| Ricin (1IFS) | 6% | 38% | 55% | 100% | **100%** |
| Anthrax LF (1J7N) | 6% | 29% | 51% | 100% | **100%** |
| BoNT (3BTA) †† | 6% | 2% | 53% | 96% | **100%** |
| Diphtheria (1BC7) †† | — | 0% | 0% | 0% | **100%** |
| **All 255 variants** | ~6% | 34.5% | 52.9% | 79.2% | **100% (AUROC 1.000)** |

†† = never seen in any training version. BoNT and Diphtheria demonstrate cross-family generalization from ESM-2 structural embeddings.

### Protein Usage

```python
import pickle, numpy as np
from huggingface_hub import hf_hub_download

# V2 — CPU, fast
prot_path = hf_hub_download("Seyomi/synthguard-kmer", "protein_kmer_model.pkl")
with open(prot_path, "rb") as f: protein_model = pickle.load(f)

_AA20 = list("ACDEFGHIKLMNPQRSTVWY")
_DIPEP = [a+b for a in _AA20 for b in _AA20]

def protein_features(aa):
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
              'T':119,'V':117,'W':204,'Y':181}.get(c, 110) for c in aa) / n
    charge = sum({'R':1,'K':1,'D':-1,'E':-1}.get(c,0) for c in aa) / n
    hydro  = sum({'A':1.8,'V':4.2,'L':3.8,'I':4.5,'P':-1.6,'F':2.8,'W':-0.9,'M':1.9,
                  'G':-0.4,'S':-0.8,'T':-0.7,'C':2.5,'Y':-1.3,'H':-3.2,'D':-3.5,
                  'E':-3.5,'N':-3.5,'Q':-3.5,'K':-3.9,'R':-4.5}.get(c,0) for c in aa)/n
    return comp + dipep_f + [hydro, charge, mw/200, 0.0, 0.0, aa.count('C')/n]

def screen_protein(aa, threshold_review=0.3, threshold_escalate=0.6):
    feats = np.array([protein_features(aa)])
    prob = float(protein_model.predict_proba(feats)[0, 1])
    if prob >= threshold_escalate: return "ESCALATE", prob
    if prob >= threshold_review:   return "REVIEW", prob
    return "SAFE", prob

decision, score = screen_protein("MKAIFVLKGFFGAFLGFLLLPFLMAK")
print(f"{decision} (score: {score:.3f})")
```

---

## Training Data

Dataset: [`Seyomi/synthscreen-dataset`](https://huggingface.co/datasets/Seyomi/synthscreen-dataset)

| Property | Value |
|----------|-------|
| Total sequences | ~14,700 |
| Organism families | 37 |
| Class balance | ~50:50 hazardous/benign |
| Split | 70% train / 15% val / 15% test |
| Test set | 2,214 sequences (1,057 haz / 1,157 benign) |

**Training hazardous families (~14):** ricin, BoNT-A/B/E, anthrax lethal factor, *Yersinia pestis*, *Clostridium perfringens* epsilon toxin, Staph enterotoxin B, Shiga toxin, VEEV capsid, Ebola GP, Marburg NP, *Burkholderia*, *Vibrio cholerae*, abrin, diphtheria toxin

**Augmentation:** 2 codon-shuffled variants per hazardous sequence (25% and 45% synonymous substitution fraction) + sliding-window fragments (50–300 bp)

**BLAST database (for benchmarking):** 741 original non-augmented training hazardous sequences — replicates the information available to real synthesis screeners.

---

## Limitations

**Report these in publications:**
- **Short sequences (<150 bp):** 76.3% recall, 16.6% FPR — k-mer distributions are unreliable at this length
- **Brucella abortus:** 85% OOD recall — obligate-intracellular high-GC codon usage diverges from training distribution
- **Chimeric constructs not evaluated:** hazardous functional domain fused to benign scaffold would dominate the codon-usage signal
- **RFdiffusion de-novo backbones not evaluated:** novel backbone + ProteinMPNN redesign may share no k-mer similarity with known toxins
- **Computational only:** no wet-lab functional validation of hazard predictions

---

## Live API

```bash
curl -X POST https://seyomi-synthguard-api.hf.space/screen \
  -H "Content-Type: application/json" \
  -d '{"sequence": "ATGGCTAGCATGACTGGT...", "threshold_review": 0.3, "threshold_escalate": 0.6}'
```

Health check: `GET https://seyomi-synthguard-api.hf.space/health`

---

## Related

- Dataset: [`Seyomi/synthscreen-dataset`](https://huggingface.co/datasets/Seyomi/synthscreen-dataset)
- Dashboard: [`Seyomi/biolens-dashboard`](https://huggingface.co/spaces/Seyomi/biolens-dashboard)
- Demo: [`Seyomi/synthguard-demo`](https://huggingface.co/spaces/Seyomi/synthguard-demo)
- Code: [github.com/Ashok-kumar290/synthscreen](https://github.com/Ashok-kumar290/synthscreen) (branch: `synthguard`)

## Citation

```
SynthGuard: Closing the AI Biodesign Gap in DNA Synthesis Screening
AIxBio Hackathon 2026 — Track 1 | Ashok Kumar
https://github.com/Ashok-kumar290/synthscreen
Benchmark: NCBI BLAST+ 2.12.0+, Google Colab A100, April 26 2026
```
