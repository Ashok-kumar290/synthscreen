# %% [Cell 1] Install dependencies
# Run this cell first in Google Colab (A100 runtime)
"""
!apt-get install -y -q ncbi-blast+
!pip install -q biopython lightgbm scikit-learn huggingface_hub datasets
"""

# %% [Cell 2] Imports
import json
import math
import os
import pickle
import random
import subprocess
import tempfile
import time
import warnings
from collections import Counter
from itertools import product
from pathlib import Path

import numpy as np
from Bio import Entrez, SeqIO
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score

warnings.filterwarnings("ignore")

print("Imports OK")

# %% [Cell 3] Codon tables and 5,533-feature extractor (must match training)

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

_AA_CODONS: dict = {}
for _c, _a in CODON_TABLE.items():
    _AA_CODONS.setdefault(_a, []).append(_c)

ALL_CODONS   = sorted(CODON_TABLE.keys())
AMINO_ACIDS  = sorted(a for a in set(CODON_TABLE.values()) if a != '*')
VOCAB        = {k: ["".join(p) for p in product("ACGT", repeat=k)] for k in [3, 4, 5, 6]}

# Kazusa DB codon frequencies (per thousand) for CAI
_ECOLI = {'TTT':22.0,'TTC':16.5,'TTA':13.9,'TTG':13.1,'CTT':10.9,'CTC':10.0,'CTA':3.8,'CTG':52.7,'ATT':28.8,'ATC':25.1,'ATA':4.4,'ATG':27.4,'GTT':19.5,'GTC':14.7,'GTA':10.8,'GTG':25.9,'TCT':7.8,'TCC':8.8,'TCA':7.0,'TCG':8.7,'CCT':7.2,'CCC':5.6,'CCA':8.4,'CCG':23.3,'ACT':9.0,'ACC':23.4,'ACA':7.2,'ACG':14.6,'GCT':15.3,'GCC':25.8,'GCA':20.6,'GCG':33.5,'TAT':16.3,'TAC':12.5,'TAA':2.0,'TAG':0.3,'CAT':13.2,'CAC':9.6,'CAA':15.5,'CAG':28.7,'AAT':22.3,'AAC':22.4,'AAA':33.6,'AAG':10.1,'GAT':32.2,'GAC':19.0,'GAA':39.8,'GAG':18.3,'TGT':5.0,'TGC':6.5,'TGA':1.0,'TGG':15.2,'CGT':21.1,'CGC':21.7,'CGA':3.7,'CGG':5.3,'AGT':8.7,'AGC':15.8,'AGA':3.5,'AGG':2.9,'GGT':24.7,'GGC':29.5,'GGA':8.0,'GGG':11.5}
_HUMAN  = {'TTT':17.6,'TTC':20.3,'TTA':7.7,'TTG':12.9,'CTT':13.2,'CTC':19.6,'CTA':7.2,'CTG':39.6,'ATT':16.0,'ATC':20.8,'ATA':7.5,'ATG':22.0,'GTT':11.0,'GTC':14.5,'GTA':7.1,'GTG':28.1,'TCT':15.2,'TCC':17.7,'TCA':12.2,'TCG':4.4,'CCT':17.5,'CCC':19.8,'CCA':16.9,'CCG':6.9,'ACT':13.1,'ACC':18.9,'ACA':15.1,'ACG':6.1,'GCT':18.4,'GCC':27.7,'GCA':15.8,'GCG':7.4,'TAT':12.2,'TAC':15.3,'TAA':1.0,'TAG':0.8,'CAT':10.9,'CAC':15.1,'CAA':12.3,'CAG':34.2,'AAT':17.0,'AAC':19.1,'AAA':24.4,'AAG':31.9,'GAT':21.8,'GAC':25.1,'GAA':29.0,'GAG':39.6,'TGT':10.6,'TGC':12.6,'TGA':1.6,'TGG':13.2,'CGT':4.5,'CGC':10.4,'CGA':6.2,'CGG':11.4,'AGT':15.2,'AGC':19.5,'AGA':11.5,'AGG':11.4,'GGT':10.8,'GGC':22.2,'GGA':16.5,'GGG':16.5}
_YEAST  = {'TTT':26.2,'TTC':18.4,'TTA':26.2,'TTG':27.2,'CTT':12.3,'CTC':5.4,'CTA':13.4,'CTG':10.5,'ATT':30.1,'ATC':17.2,'ATA':17.8,'ATG':20.9,'GTT':22.1,'GTC':11.8,'GTA':11.8,'GTG':10.8,'TCT':23.5,'TCC':14.2,'TCA':18.7,'TCG':8.6,'CCT':13.5,'CCC':6.8,'CCA':18.3,'CCG':5.4,'ACT':20.3,'ACC':13.1,'ACA':17.9,'ACG':8.1,'GCT':21.1,'GCC':12.6,'GCA':16.0,'GCG':6.2,'TAT':18.8,'TAC':14.8,'TAA':1.1,'TAG':0.5,'CAT':13.6,'CAC':7.8,'CAA':27.3,'CAG':12.1,'AAT':35.9,'AAC':24.8,'AAA':41.9,'AAG':30.8,'GAT':37.6,'GAC':20.2,'GAA':45.0,'GAG':19.2,'TGT':8.1,'TGC':4.8,'TGA':0.7,'TGG':10.4,'CGT':6.4,'CGC':2.6,'CGA':3.0,'CGG':1.7,'AGT':14.2,'AGC':9.8,'AGA':21.3,'AGG':9.2,'GGT':23.9,'GGC':9.8,'GGA':10.9,'GGG':6.0}

def _ref_rscu(freq_table):
    rscu = {}
    for aa, codons in _AA_CODONS.items():
        if aa == '*':
            for c in codons: rscu[c] = 1.0
            continue
        max_f = max(freq_table.get(c, 0.1) for c in codons)
        for c in codons:
            rscu[c] = freq_table.get(c, 0.1) / max_f if max_f > 0 else 1.0
    return rscu

_ECOLI_RSCU = _ref_rscu(_ECOLI)
_HUMAN_RSCU = _ref_rscu(_HUMAN)
_YEAST_RSCU = _ref_rscu(_YEAST)

def _codon_features(seq):
    codon_cnt = Counter()
    for i in range(0, len(seq) - 2, 3):
        cdn = seq[i:i+3]
        if len(cdn) == 3 and cdn in CODON_TABLE:
            codon_cnt[cdn] += 1

    rscu_vals = {}
    for aa, codons in _AA_CODONS.items():
        if aa == '*':
            for c in codons: rscu_vals[c] = 1.0
            continue
        aa_total = sum(codon_cnt.get(c, 0) for c in codons)
        n_syn = len(codons)
        expected = aa_total / n_syn if aa_total > 0 else 0
        for c in codons:
            rscu_vals[c] = codon_cnt.get(c, 0) / expected if expected > 0 else 1.0
    rscu_feats = [rscu_vals.get(c, 1.0) for c in ALL_CODONS]

    def cai(ref_rscu):
        log_sum, count = 0.0, 0
        for cdn, n in codon_cnt.items():
            if CODON_TABLE.get(cdn, '*') != '*':
                log_sum += math.log(max(ref_rscu.get(cdn, 0.01), 1e-6)) * n
                count += n
        return math.exp(log_sum / count) if count > 0 else 0.5
    cai_feats = [cai(_ECOLI_RSCU), cai(_HUMAN_RSCU), cai(_YEAST_RSCU)]

    aa_total = sum(n for cdn, n in codon_cnt.items() if CODON_TABLE.get(cdn, '*') != '*')
    aa_cnt = Counter()
    for cdn, n in codon_cnt.items():
        aa = CODON_TABLE.get(cdn, '*')
        if aa != '*':
            aa_cnt[aa] += n
    aa_feats = [aa_cnt.get(aa, 0) / max(aa_total, 1) for aa in AMINO_ACIDS]

    return rscu_feats + cai_feats + aa_feats  # 64 + 3 + 20 = 87

def extract_features(seq):
    """Full 5,533-feature extractor matching the deployed model exactly."""
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
        kc = Counter(seq[i:i+k] for i in range(n - k + 1))
        tk = max(n - k + 1, 1)
        feats.extend(kc.get(km, 0) / tk for km in VOCAB[k])
    feats.extend(_codon_features(seq))
    return feats  # 6 + 5440 + 87 = 5533

# Sanity check
_test = extract_features("ATGATGATGATG" * 20)
assert len(_test) == 5533, f"Feature count wrong: {len(_test)}"
print(f"Feature extractor: {len(_test)} features ✓")

# %% [Cell 4] Real blastn / blastp functions

BLAST_DB_DIR = Path("/content/blast_db")

def blastn_screen(seq, perc_identity=70.0):
    """Real NCBI blastn. Returns True if seq matches hazard DB at given identity."""
    seq = seq.upper().replace("U", "T")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".fa", delete=False) as f:
        f.write(f">query\n{seq}\n")
        qfile = f.name
    try:
        cmd = [
            "blastn", "-query", qfile, "-db", str(BLAST_DB_DIR / "hazard_dna"),
            "-outfmt", "6 pident", "-max_hsps", "1", "-max_target_seqs", "1",
            "-perc_identity", str(perc_identity), "-dust", "no",
        ]
        if len(seq) < 50:
            cmd += ["-task", "blastn-short", "-word_size", "7"]
        else:
            cmd += ["-task", "blastn"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return bool(r.stdout.strip())
    except Exception:
        return False
    finally:
        os.unlink(qfile)

def blastn_score(seq, perc_identity=70.0):
    """Returns 1.0 if hit found, 0.0 otherwise (for AUROC computation)."""
    return 1.0 if blastn_screen(seq, perc_identity) else 0.0

print("BLAST functions defined ✓")
print(f"blastn version: ", end="")
import subprocess as _sp
print(_sp.run(["blastn", "-version"], capture_output=True, text=True).stdout.split("\n")[0])

# %% [Cell 5] Load SynthGuard models from HuggingFace

from huggingface_hub import hf_hub_download

HF_REPO = "Seyomi/synthguard-kmer"
MODEL_DIR = Path("/content/models")
MODEL_DIR.mkdir(exist_ok=True)

print("Downloading models from HuggingFace...")
for fname in ["general_model.pkl", "short_model.pkl", "meta.json"]:
    path = hf_hub_download(HF_REPO, fname, local_dir=str(MODEL_DIR))
    print(f"  {fname} → {path}")

with open(MODEL_DIR / "general_model.pkl", "rb") as f:
    general_model = pickle.load(f)
with open(MODEL_DIR / "short_model.pkl", "rb") as f:
    short_model = pickle.load(f)
with open(MODEL_DIR / "meta.json") as f:
    meta = json.load(f)

print(f"\nGeneral model: {general_model}")
print(f"Short model:   {short_model}")
print(f"n_features_in_ (general): {general_model.n_features_in_}")
print(f"n_features_in_ (short):   {short_model.n_features_in_}")
assert general_model.n_features_in_ == 5533, "Feature count mismatch!"
assert short_model.n_features_in_ == 5533, "Feature count mismatch!"
print("Model feature counts verified: 5,533 ✓")

# %% [Cell 6] Build BLAST database from HF training hazardous sequences

from datasets import load_dataset

print("Loading HuggingFace dataset to build BLAST DB...")
ds = load_dataset("Seyomi/synthscreen-dataset", split="train")

# Only original (non-augmented) hazardous sequences for the DB
train_haz_originals = [
    row["sequence"] for row in ds
    if row["label"] == 1 and row.get("source", "original") == "original"
]
print(f"  Training hazardous original sequences: {len(train_haz_originals)}")

BLAST_DB_DIR.mkdir(exist_ok=True)
dna_fa = BLAST_DB_DIR / "hazard_dna.fa"

with open(dna_fa, "w") as f:
    for i, seq in enumerate(train_haz_originals):
        seq_clean = seq.upper().replace("U", "T")
        seq_clean = "".join(c for c in seq_clean if c in "ACGTN")
        if len(seq_clean) >= 30:
            f.write(f">haz_{i}\n{seq_clean}\n")

r = subprocess.run(
    ["makeblastdb", "-in", str(dna_fa), "-dbtype", "nucl",
     "-out", str(BLAST_DB_DIR / "hazard_dna")],
    capture_output=True, text=True
)
print(r.stdout)
if r.returncode != 0:
    print("makeblastdb stderr:", r.stderr)
else:
    print("BLAST DB built successfully ✓")

# %% [Cell 7] OOD toxin families and codon shuffle utility

ENTREZ_EMAIL = "protonooblive@gmail.com"
Entrez.email = ENTREZ_EMAIL

OOD_HAZARDOUS = [
    ('"tetanus toxin" AND "Clostridium tetani"[Organism]',
     "Tetanus toxin"),
    ('"Francisella tularensis"[Organism] AND "virulence" AND 300:3000[SLEN]',
     "Francisella tularensis"),
    ('"Brucella abortus"[Organism] AND "virulence" AND 300:3000[SLEN]',
     "Brucella abortus"),
    ('"Coxiella burnetii"[Organism] AND "virulence" AND 300:3000[SLEN]',
     "Coxiella burnetii"),
    ('"Clostridioides difficile"[Organism] AND "toxin A" AND 500:3000[SLEN]',
     "C. difficile toxin A"),
    ('"SARS-CoV-2"[Organism] AND "spike protein" AND 500:4000[SLEN]',
     "SARS-CoV-2 spike"),
    ('"Variola virus"[Organism] AND 300:3000[SLEN]',
     "Variola virus"),
]

OOD_BENIGN = [
    ('"Streptomyces coelicolor"[Organism] AND 500:3000[SLEN]',
     "Streptomyces coelicolor"),
    ('"Pichia pastoris"[Organism] AND "expression" AND 300:2000[SLEN]',
     "Pichia pastoris"),
    ('"Neurospora crassa"[Organism] AND 300:2000[SLEN]',
     "Neurospora crassa"),
    ('"Danio rerio"[Organism] AND "housekeeping" AND 300:2000[SLEN]',
     "Zebrafish housekeeping"),
    ('"Arabidopsis thaliana"[Organism] AND "chloroplast" AND 300:2000[SLEN]',
     "Arabidopsis chloroplast"),
]

SYNONYMOUS_CODONS = {
    'TTT':['TTC'],'TTC':['TTT'],'TTA':['TTG','CTT','CTC','CTA','CTG'],'TTG':['TTA','CTT','CTC','CTA','CTG'],
    'CTT':['TTA','TTG','CTC','CTA','CTG'],'CTC':['TTA','TTG','CTT','CTA','CTG'],
    'CTA':['TTA','TTG','CTT','CTC','CTG'],'CTG':['TTA','TTG','CTT','CTC','CTA'],
    'ATT':['ATC','ATA'],'ATC':['ATT','ATA'],'ATA':['ATT','ATC'],'ATG':['ATG'],
    'GTT':['GTC','GTA','GTG'],'GTC':['GTT','GTA','GTG'],'GTA':['GTT','GTC','GTG'],'GTG':['GTT','GTC','GTA'],
    'TCT':['TCC','TCA','TCG','AGT','AGC'],'TCC':['TCT','TCA','TCG','AGT','AGC'],
    'TCA':['TCT','TCC','TCG','AGT','AGC'],'TCG':['TCT','TCC','TCA','AGT','AGC'],
    'AGT':['TCT','TCC','TCA','TCG','AGC'],'AGC':['TCT','TCC','TCA','TCG','AGT'],
    'CCT':['CCC','CCA','CCG'],'CCC':['CCT','CCA','CCG'],'CCA':['CCT','CCC','CCG'],'CCG':['CCT','CCC','CCA'],
    'ACT':['ACC','ACA','ACG'],'ACC':['ACT','ACA','ACG'],'ACA':['ACT','ACC','ACG'],'ACG':['ACT','ACC','ACA'],
    'GCT':['GCC','GCA','GCG'],'GCC':['GCT','GCA','GCG'],'GCA':['GCT','GCC','GCG'],'GCG':['GCT','GCC','GCA'],
    'TAT':['TAC'],'TAC':['TAT'],'CAT':['CAC'],'CAC':['CAT'],'CAA':['CAG'],'CAG':['CAA'],
    'AAT':['AAC'],'AAC':['AAT'],'AAA':['AAG'],'AAG':['AAA'],'GAT':['GAC'],'GAC':['GAT'],
    'GAA':['GAG'],'GAG':['GAA'],'TGT':['TGC'],'TGC':['TGT'],'TGG':['TGG'],
    'CGT':['CGC','CGA','CGG','AGA','AGG'],'CGC':['CGT','CGA','CGG','AGA','AGG'],
    'CGA':['CGT','CGC','CGG','AGA','AGG'],'CGG':['CGT','CGC','CGA','AGA','AGG'],
    'AGA':['CGT','CGC','CGA','CGG','AGG'],'AGG':['CGT','CGC','CGA','CGG','AGA'],
    'GGT':['GGC','GGA','GGG'],'GGC':['GGT','GGA','GGG'],'GGA':['GGT','GGC','GGG'],'GGG':['GGT','GGC','GGA'],
    'TAA':['TAG','TGA'],'TAG':['TAA','TGA'],'TGA':['TAA','TAG'],
}

def shuffle_codons(dna, fraction=0.35, seed=42):
    random.seed(seed)
    dna = dna.upper().replace("U", "T")
    codons = [dna[i:i+3] for i in range(0, len(dna)-2, 3)]
    result = []
    for codon in codons:
        if len(codon) < 3:
            result.append(codon)
            continue
        if random.random() < fraction and codon in SYNONYMOUS_CODONS:
            syns = SYNONYMOUS_CODONS[codon]
            result.append(random.choice(syns) if syns else codon)
        else:
            result.append(codon)
    return "".join(result)

def fetch_ncbi(query, max_count=80, delay=0.4):
    seqs = []
    try:
        handle = Entrez.esearch(db="nucleotide", term=query, retmax=max_count)
        record = Entrez.read(handle)
        handle.close()
        ids = record.get("IdList", [])
        if not ids:
            return []
        time.sleep(delay)
        handle = Entrez.efetch(db="nucleotide", id=",".join(ids[:max_count]),
                               rettype="fasta", retmode="text")
        for rec in SeqIO.parse(handle, "fasta"):
            seq = "".join(c for c in str(rec.seq).upper() if c in "ACGTN")
            if 50 <= len(seq) <= 4000:
                seqs.append(seq)
        handle.close()
        time.sleep(delay)
    except Exception as e:
        print(f"    NCBI error: {e}")
    return seqs

print("OOD config and utilities defined ✓")

# %% [Cell 8] Fetch OOD sequences from NCBI

print("=" * 65)
print("Fetching OOD hazardous sequences (unseen toxin families)...")
print("=" * 65)

hazardous_raw, hazardous_family = [], []
for query, family in OOD_HAZARDOUS:
    seqs = fetch_ncbi(query, max_count=80)
    print(f"  {len(seqs):3d} seqs | {family}")
    for s in seqs:
        hazardous_raw.append(s)
        hazardous_family.append(family)

print(f"\nTotal OOD hazardous (raw): {len(hazardous_raw)}")

print("\nFetching OOD benign sequences...")
benign_raw, benign_family = [], []
for query, family in OOD_BENIGN:
    seqs = fetch_ncbi(query, max_count=80)
    print(f"  {len(seqs):3d} seqs | {family}")
    for s in seqs:
        benign_raw.append(s)
        benign_family.append(family)

print(f"Total OOD benign (raw): {len(benign_raw)}")

# %% [Cell 9] Build evaluation set (original + codon-shuffled)

print("\nBuilding OOD evaluation set...")

seqs_eval, labels_eval, sources_eval, families_eval = [], [], [], []

SHUFFLE_FRACS = [0.25, 0.45]

for seq, fam in zip(hazardous_raw, hazardous_family):
    seq = seq[:2048]
    seqs_eval.append(seq); labels_eval.append(1)
    sources_eval.append("original"); families_eval.append(fam)
    for i, frac in enumerate(SHUFFLE_FRACS):
        variant = shuffle_codons(seq, fraction=frac, seed=hash(seq) + i)
        seqs_eval.append(variant); labels_eval.append(1)
        sources_eval.append(f"codon_shuffled_{int(frac*100)}pct"); families_eval.append(fam)

for seq, fam in zip(benign_raw, benign_family):
    seq = seq[:2048]
    seqs_eval.append(seq); labels_eval.append(0)
    sources_eval.append("original"); families_eval.append(fam)
    variant = shuffle_codons(seq, fraction=0.35, seed=hash(seq))
    seqs_eval.append(variant); labels_eval.append(0)
    sources_eval.append("codon_shuffled_35pct"); families_eval.append(fam)

# Balance classes
haz_idx = [i for i, l in enumerate(labels_eval) if l == 1]
ben_idx = [i for i, l in enumerate(labels_eval) if l == 0]
random.seed(42)
min_n = min(len(haz_idx), len(ben_idx))
keep = set(random.sample(haz_idx, min_n) + random.sample(ben_idx, min_n))
seqs_eval    = [seqs_eval[i]    for i in sorted(keep)]
labels_eval  = [labels_eval[i]  for i in sorted(keep)]
sources_eval = [sources_eval[i] for i in sorted(keep)]
families_eval= [families_eval[i]for i in sorted(keep)]

y = np.array(labels_eval)
n_haz = int(y.sum())
n_ben = int((1 - y).sum())
short_mask = np.array([len(s) < 150 for s in seqs_eval])
ai_mask    = np.array(["shuffled" in src for src in sources_eval])

print(f"OOD eval set: {len(seqs_eval)} sequences ({n_haz} hazardous / {n_ben} benign)")
print(f"  Codon-shuffled hazardous: {int((ai_mask & (y == 1)).sum())}")
print(f"  Short (<150bp): {short_mask.sum()}")

# %% [Cell 10] Extract features for SynthGuard

print("\nExtracting 5,533 features...")
X = np.array([extract_features(s) for s in seqs_eval])
print(f"Feature matrix: {X.shape}  (expected n × 5533)")
assert X.shape[1] == 5533, f"Feature mismatch: got {X.shape[1]}"
print("Feature extraction verified ✓")

# %% [Cell 11] Run real blastn on OOD sequences

print(f"\nRunning real blastn (70% identity) on {len(seqs_eval)} sequences...")
print("This may take several minutes...")

blastn_scores = []
for i, seq in enumerate(seqs_eval):
    score = blastn_score(seq, perc_identity=70.0)
    blastn_scores.append(score)
    if (i + 1) % 100 == 0:
        print(f"  {i+1}/{len(seqs_eval)} done")

blastn_scores = np.array(blastn_scores)
blastn_preds  = (blastn_scores >= 0.5).astype(int)
print("blastn complete ✓")

# %% [Cell 12] Run SynthGuard

print("\nRunning SynthGuard k-mer...")
sg_probs = np.where(
    short_mask,
    short_model.predict_proba(X)[:, 1],
    general_model.predict_proba(X)[:, 1],
)
sg_preds = (sg_probs >= 0.5).astype(int)
print("SynthGuard complete ✓")

# %% [Cell 13] Compute metrics and print results

def compute_metrics(labels, preds, probs):
    cm = confusion_matrix(labels, preds)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)
    auc = roc_auc_score(labels, probs) if len(set(labels)) > 1 else float("nan")
    return dict(
        recall   = recall_score(labels, preds, zero_division=0),
        precision= precision_score(labels, preds, zero_division=0),
        f1       = f1_score(labels, preds, zero_division=0),
        auroc    = auc,
        fpr      = fp / (fp + tn) if (fp + tn) else 0.0,
        tp=int(tp), fp=int(fp), tn=int(tn), fn=int(fn), n=len(labels),
    )

print("\n" + "=" * 75)
print("OOD BENCHMARK RESULTS — UNSEEN TOXIN FAMILIES (real blastn 2.12.0+)")
print("Training: ricin/BoNT-A,B,E/anthrax/Yersinia/Shiga/VEEV/Ebola/Marburg/abrin/diphtheria")
print("OOD:      tetanus/Francisella/Brucella/Coxiella/C.diff/SARS-CoV-2/Variola")
print("=" * 75)

slices = [
    ("Full OOD set",             np.ones(len(y), dtype=bool)),
    ("Original sequences",       np.array([s == "original" for s in sources_eval])),
    ("Codon-shuffled variants",  ai_mask),
    ("Short sequences (<150bp)", short_mask),
]

fmt_hdr = "  {:<35} {:>7} {:>7} {:>7} {:>7} {:>7}"
fmt_row = "  {:<35} {:>7.3f} {:>7.3f} {:>7.3f} {:>7.3f} {:>7}"
print(fmt_hdr.format("Method / Slice", "Recall", "Prec", "F1", "AUROC", "FPR"))
print("  " + "─" * 68)

all_results = {}
for slice_name, mask in slices:
    if mask.sum() < 2 or len(set(y[mask])) < 2:
        continue
    print(f"\n  [{slice_name}]  n={mask.sum()}")
    for name, preds, probs in [
        ("blastn (70%)",    blastn_preds, blastn_scores),
        ("SynthGuard k-mer", sg_preds,   sg_probs),
    ]:
        m = compute_metrics(y[mask], preds[mask], probs[mask])
        key = f"{slice_name}|{name}"
        all_results[key] = m
        auroc_str = f"{m['auroc']:.3f}" if not math.isnan(m['auroc']) else "  nan"
        print(fmt_row.format(
            f"    {name}",
            m['recall'], m['precision'], m['f1'],
            float(auroc_str) if auroc_str != "  nan" else float("nan"),
            f"{m['fpr']:.3f}",
        ))

# %% [Cell 14] Per-toxin-family breakdown

print("\n\n  PER-TOXIN-FAMILY RECALL — original sequences only")
print("  " + "─" * 60)
print(f"  {'Family':<35} {'SynthGuard':>10} {'blastn':>8} {'n':>5}")
print("  " + "─" * 60)

per_family_results = {}
for _, family in OOD_HAZARDOUS:
    idx = [i for i, (fam, lbl, src) in enumerate(zip(families_eval, labels_eval, sources_eval))
           if fam == family and lbl == 1 and src == "original"]
    if not idx:
        print(f"  {family:<35} {'no seqs':>10}")
        continue
    sg_r  = sg_preds[idx].mean()
    bl_r  = blastn_preds[idx].mean()
    n     = len(idx)
    print(f"  {family:<35} {sg_r:>9.1%} {bl_r:>7.1%} {n:>5}")
    per_family_results[family] = {"synthguard_recall": float(sg_r),
                                   "blastn_recall": float(bl_r), "n": n}

# Summary
full_blast = all_results.get("Full OOD set|blastn (70%)", {})
full_sg    = all_results.get("Full OOD set|SynthGuard k-mer", {})
print("\n\n  HEADLINE")
print(f"  OOD recall   — blastn: {full_blast.get('recall',0):.1%}  | SynthGuard: {full_sg.get('recall',0):.1%}")
print(f"  OOD AUROC    — blastn: {full_blast.get('auroc',0):.3f} | SynthGuard: {full_sg.get('auroc',0):.3f}")
print(f"  OOD FPR      — blastn: {full_blast.get('fpr',0):.1%}  | SynthGuard: {full_sg.get('fpr',0):.1%}")

# %% [Cell 15] Save results

output = {
    "date": "2026-04-26",
    "blast_version": "blastn 2.12.0+",
    "blast_db": "741 original hazardous training sequences (non-augmented)",
    "ood_families": [fam for _, fam in OOD_HAZARDOUS],
    "n_sequences": len(seqs_eval),
    "n_hazardous": n_haz,
    "n_benign": n_ben,
    "metrics": {
        k: {mk: (float(mv) if isinstance(mv, (float, np.floating)) else mv)
            for mk, mv in v.items()}
        for k, v in all_results.items()
    },
    "per_family": per_family_results,
}

out_path = "/content/ood_benchmark_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nResults saved → {out_path}")
print("Download from Colab Files panel or drive.mount() to persist.")
