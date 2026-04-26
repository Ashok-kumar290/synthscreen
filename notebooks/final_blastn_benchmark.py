# ============================================================
#  SynthGuard — Final BLAST Benchmark (Real blastn / blastp)
#  Google Colab · A100 · April 2026
#
#  PURPOSE:
#    Definitively benchmark SynthGuard LightGBM models (pulled
#    from HuggingFace) against REAL NCBI BLAST+ (blastn for DNA,
#    blastp for protein).  No proxy. No k-mer Jaccard.
#
#  PASTE EACH CELL BLOCK into Colab in order.
# ============================================================


# ── CELL 1 ── Install NCBI BLAST+ and verify version ─────────────────────────

import subprocess, sys

print("Installing NCBI BLAST+...")
subprocess.run(["apt-get", "install", "-y", "-q", "ncbi-blast+"], check=True)

# Verify — this is the line we log for the paper
result = subprocess.run(["blastn", "-version"], capture_output=True, text=True)
print(result.stdout.strip())
result2 = subprocess.run(["blastp", "-version"], capture_output=True, text=True)
print(result2.stdout.strip())


# ── CELL 2 ── Install Python packages ────────────────────────────────────────

subprocess.run([sys.executable, "-m", "pip", "install", "-q",
    "datasets", "huggingface_hub", "lightgbm", "scikit-learn",
    "numpy", "pandas", "matplotlib", "biopython"], check=True)

print("Packages ready.")


# ── CELL 3 ── Download models from HuggingFace ───────────────────────────────

import os, pickle, json
from huggingface_hub import hf_hub_download

REPO = "Seyomi/synthguard-kmer"
MODEL_DIR = "/content/models"
os.makedirs(MODEL_DIR, exist_ok=True)

for fname in ["general_model.pkl", "short_model.pkl",
              "protein_kmer_model.pkl", "meta.json"]:
    path = hf_hub_download(repo_id=REPO, filename=fname,
                           local_dir=MODEL_DIR)
    print(f"  Downloaded: {path}")

# Load models
with open(f"{MODEL_DIR}/general_model.pkl", "rb") as f:
    general_model = pickle.load(f)
with open(f"{MODEL_DIR}/short_model.pkl", "rb") as f:
    short_model = pickle.load(f)
with open(f"{MODEL_DIR}/protein_kmer_model.pkl", "rb") as f:
    protein_model = pickle.load(f)
with open(f"{MODEL_DIR}/meta.json") as f:
    meta = json.load(f)

print(f"\nDNA general model: {general_model}")
print(f"DNA short model:   {short_model}")
print(f"Protein model:     {protein_model}")
print(f"Meta: {meta}")


# ── CELL 4 ── Download dataset from HuggingFace ──────────────────────────────

from datasets import load_dataset

print("Loading dataset Seyomi/synthscreen-dataset ...")
ds = load_dataset("Seyomi/synthscreen-dataset")
print(ds)
print(f"\nSplits: {list(ds.keys())}")
for split in ds:
    labels = ds[split]["label"]
    n_haz = sum(labels)
    print(f"  {split}: {len(ds[split])} seqs, {n_haz} hazardous, "
          f"{len(ds[split])-n_haz} benign")

# Inspect source field
sample_sources = set(ds["train"]["source"][:200])
print(f"\nSample source tags (train): {sample_sources}")


# ── CELL 5 ── Build BLAST DNA hazard database ─────────────────────────────────
#
# Use ONLY original (non-augmented) hazardous training sequences.
# This replicates real-world synthesis screening: BLAST database =
# known hazardous sequences deposited in GenBank/select-agent registries.
# It does NOT include codon-shuffled or ProteinMPNN variants.

DB_DIR = "/content/blast_db"
os.makedirs(DB_DIR, exist_ok=True)

# Filter original hazardous training sequences
# Adapt source-filter logic to actual source tags in your dataset
ORIGINAL_TAGS = {"original", "natural", "ncbi", "genbank", "uniprot"}

train_data = ds["train"]
original_haz_seqs = []
for row in train_data:
    if row["label"] == 1:
        src = str(row.get("source", "")).lower()
        # Include if source is original (not codon_shuffled, not mpnn/proteinmpnn)
        if not any(t in src for t in ["codon", "shuffled", "mpnn", "variant",
                                       "fragment", "augment", "redesign"]):
            original_haz_seqs.append(row["sequence"])

print(f"Original hazardous training sequences: {len(original_haz_seqs)}")

# Write FASTA
dna_fasta = f"{DB_DIR}/hazard_dna.fasta"
with open(dna_fasta, "w") as f:
    for i, seq in enumerate(original_haz_seqs):
        f.write(f">hazard_{i}\n{seq}\n")

# Build blastn database
result = subprocess.run([
    "makeblastdb", "-in", dna_fasta, "-dbtype", "nucl",
    "-out", f"{DB_DIR}/hazard_dna", "-title", "SynthGuard_Hazard_DNA"
], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr)
else:
    print("DNA BLAST database built successfully.")
    print(f"Sequences in DB: {len(original_haz_seqs)}")


# ── CELL 6 ── Build BLAST protein hazard database ─────────────────────────────

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

def translate_best_frame(dna: str) -> str:
    dna = dna.upper().replace("U", "T")
    best = ""
    for frame in range(3):
        aa = "".join(CODON_TABLE.get(dna[i:i+3], "X")
                     for i in range(frame, len(dna)-2, 3))
        if "*" in aa:
            aa = aa[:aa.index("*")]
        if len(aa) > len(best):
            best = aa
    return best

# Translate original hazardous sequences → protein
original_haz_proteins = []
for seq in original_haz_seqs:
    prot = translate_best_frame(seq)
    if len(prot) >= 30:
        original_haz_proteins.append(prot)

print(f"Translatable original hazardous seqs: {len(original_haz_proteins)}")

prot_fasta = f"{DB_DIR}/hazard_prot.fasta"
with open(prot_fasta, "w") as f:
    for i, prot in enumerate(original_haz_proteins):
        f.write(f">hazard_prot_{i}\n{prot}\n")

result = subprocess.run([
    "makeblastdb", "-in", prot_fasta, "-dbtype", "prot",
    "-out", f"{DB_DIR}/hazard_prot", "-title", "SynthGuard_Hazard_Prot"
], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr)
else:
    print("Protein BLAST database built successfully.")


# ── CELL 7 ── Feature extraction (5,533 features — must match training) ───────

import math
from collections import Counter
from itertools import product

VOCAB = {k: ["".join(p) for p in product("ACGT", repeat=k)] for k in [3, 4, 5, 6]}

_AA_CODONS: dict = {}
for _c, _aa in CODON_TABLE.items():
    _AA_CODONS.setdefault(_aa, []).append(_c)

ALL_CODONS  = sorted(CODON_TABLE.keys())
AMINO_ACIDS = sorted(a for a in set(CODON_TABLE.values()) if a != '*')

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
    aa_total = sum(n for cdn, n in codon_cnt.items() if CODON_TABLE.get(cdn,'*') != '*')
    aa_cnt = Counter()
    for cdn, n in codon_cnt.items():
        aa = CODON_TABLE.get(cdn, '*')
        if aa != '*': aa_cnt[aa] += n
    aa_feats = [aa_cnt.get(aa, 0) / max(aa_total, 1) for aa in AMINO_ACIDS]
    return rscu_feats + cai_feats + aa_feats

def extract_dna_features(seq: str) -> list:
    seq = seq.upper().replace("U", "T")
    n = max(len(seq), 1)
    cnt = Counter(seq)
    total = sum(cnt.values())
    feats = [
        n,
        (cnt.get("G",0) + cnt.get("C",0)) / n,
        (cnt.get("A",0) + cnt.get("T",0)) / n,
        cnt.get("N",0) / n,
        max(cnt.values()) / n if cnt else 0,
        -sum((c/total)*math.log2(c/total) for c in cnt.values() if c > 0),
    ]
    for k in [3, 4, 5, 6]:
        kc = Counter(seq[i:i+k] for i in range(n-k+1))
        tk = max(n-k+1, 1)
        feats.extend(kc.get(km, 0)/tk for km in VOCAB[k])
    feats.extend(_codon_features(seq))
    return feats

# Protein features (426 — AA composition + dipeptide + physicochemical)
AA_LIST = list("ACDEFGHIKLMNPQRSTVWY")
DIPEPTIDES = [a+b for a in AA_LIST for b in AA_LIST]

def extract_protein_features(aa: str) -> list:
    aa = aa.upper()
    n = max(len(aa), 1)
    # AA composition (20)
    aa_comp = [aa.count(a)/n for a in AA_LIST]
    # Dipeptide frequencies (400)
    dp_cnt = Counter(aa[i:i+2] for i in range(len(aa)-1))
    dp_total = max(sum(dp_cnt.values()), 1)
    dp_feats = [dp_cnt.get(dp, 0)/dp_total for dp in DIPEPTIDES]
    # Physicochemical (6)
    mw      = sum({'A':89,'R':174,'N':132,'D':133,'C':121,'E':147,'Q':146,
                   'G':75,'H':155,'I':131,'L':131,'K':146,'M':149,'F':165,
                   'P':115,'S':105,'T':119,'W':204,'Y':181,'V':117}.get(a,110)
                  for a in aa) / n
    charge  = (aa.count('R') + aa.count('K') - aa.count('D') - aa.count('E')) / n
    hydro   = sum({'A':1.8,'V':4.2,'I':4.5,'L':3.8,'M':1.9,'F':2.8,
                   'W':-0.9,'P':-1.6,'G':-0.4,'S':-0.8,'T':-0.7,'C':2.5,
                   'Y':-1.3,'H':-3.2,'D':-3.5,'E':-3.5,'N':-3.5,'Q':-3.5,
                   'K':-3.9,'R':-4.5}.get(a, 0) for a in aa) / n
    aromatic = (aa.count('F') + aa.count('W') + aa.count('Y')) / n
    polar    = (aa.count('S') + aa.count('T') + aa.count('N') + aa.count('Q')) / n
    cys      = aa.count('C') / n
    phys = [mw/200, charge, hydro/5, aromatic, polar, cys]
    return aa_comp + dp_feats + phys

# Verify feature counts
test_seq = "ATGATGATGATGATGATG" * 10
test_feats = extract_dna_features(test_seq)
print(f"DNA feature count: {len(test_feats)}  (expected 5533)")
assert len(test_feats) == 5533, f"MISMATCH: got {len(test_feats)}"

test_prot = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKRQTLGQHDFSAGEGLYTHMKALRPDEDRLSPLHSVYVDQWDWERVMGDGERQFSTLKSTVEAIWAGIKATEAAVSEEFGLAPFLPDQIHFVHSQELLSRYPDLDAKGRERAIAKDLGAVFLVGIGGKLSDGHRHDVRAPDYDDWSTPSELGHAGLNGDILVWNPVLEDAFELSSMGIRVDADTLKHQLALTGDEDRLELEWHQALLRGEMPQTIGGGIGQSRLTMLLLQLPHIGQVQAGVWPAAVRESVPSLL"
test_pfeats = extract_protein_features(test_prot)
print(f"Protein feature count: {len(test_pfeats)}  (expected 426)")
assert len(test_pfeats) == 426, f"MISMATCH: got {len(test_pfeats)}"


# ── CELL 8 ── Real blastn / blastp screening functions ───────────────────────

import tempfile, numpy as np
from pathlib import Path

DNA_DB   = f"{DB_DIR}/hazard_dna"
PROT_DB  = f"{DB_DIR}/hazard_prot"

def blastn_screen(seq: str, perc_identity: float = 70.0,
                  short: bool = False) -> bool:
    """
    Real blastn against the hazard database.
    Returns True if a hit ≥ perc_identity is found.
    """
    seq = seq.upper().replace("U", "T")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta",
                                     delete=False) as f:
        f.write(f">query\n{seq}\n")
        qfile = f.name
    try:
        cmd = [
            "blastn",
            "-query", qfile,
            "-db", DNA_DB,
            "-outfmt", "6 pident",
            "-max_hsps", "1",
            "-max_target_seqs", "1",
            "-perc_identity", str(perc_identity),
            "-dust", "no",
        ]
        if short or len(seq) < 50:
            cmd += ["-task", "blastn-short", "-word_size", "7"]
        else:
            cmd += ["-task", "blastn"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return bool(result.stdout.strip())
    except subprocess.TimeoutExpired:
        return False
    finally:
        os.unlink(qfile)

def blastp_screen(aa: str, perc_identity: float = 50.0) -> bool:
    """
    Real blastp against the protein hazard database.
    Returns True if a hit ≥ perc_identity is found.
    """
    if not aa or len(aa) < 10:
        return False
    with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta",
                                     delete=False) as f:
        f.write(f">query\n{aa}\n")
        qfile = f.name
    try:
        result = subprocess.run([
            "blastp",
            "-query", qfile,
            "-db", PROT_DB,
            "-outfmt", "6 pident",
            "-max_hsps", "1",
            "-max_target_seqs", "1",
            "-perc_identity", str(perc_identity),
            "-seg", "no",
        ], capture_output=True, text=True, timeout=30)
        return bool(result.stdout.strip())
    except subprocess.TimeoutExpired:
        return False
    finally:
        os.unlink(qfile)


# ── CELL 9 ── Prepare test set ────────────────────────────────────────────────

import numpy as np
from sklearn.metrics import (recall_score, precision_score, f1_score,
                              roc_auc_score, confusion_matrix)

test_data  = ds["test"]
seqs_test  = [r["sequence"] for r in test_data]
labels_test= [r["label"]    for r in test_data]
sources_test=[r.get("source","unknown") for r in test_data]

n_total = len(seqs_test)
n_haz   = sum(labels_test)
print(f"Test set: {n_total} sequences | {n_haz} hazardous | {n_total-n_haz} benign")
print(f"Unique sources: {set(sources_test)}")

# Slice masks
short_mask   = np.array([len(s) < 150 for s in seqs_test])
codon_mask   = np.array([any(t in str(src).lower()
                             for t in ["codon","shuffled"])
                         for src in sources_test])
mpnn_mask    = np.array([any(t in str(src).lower()
                             for t in ["mpnn","proteinmpnn","redesign","variant"])
                         for src in sources_test])
frag_mask    = np.array([any(t in str(src).lower()
                             for t in ["fragment","frag"])
                         for src in sources_test])
ai_mask      = codon_mask | mpnn_mask | frag_mask  # all AI-generated

print(f"\nSlice sizes:")
print(f"  Short (<150bp):        {short_mask.sum()}")
print(f"  Codon-shuffled:        {codon_mask.sum()}")
print(f"  ProteinMPNN variants:  {mpnn_mask.sum()}")
print(f"  Fragment-augmented:    {frag_mask.sum()}")
print(f"  Any AI-generated:      {ai_mask.sum()}")


# ── CELL 10 ── Extract SynthGuard features and predict ────────────────────────

print("Extracting 5,533 DNA features for test set (this takes ~3–5 min)...")
import time
t0 = time.time()
X_test = np.array([extract_dna_features(s) for s in seqs_test])
print(f"Done in {time.time()-t0:.1f}s  shape={X_test.shape}")

# Verify model expects same n_features
n_feat_model = general_model.estimators_[0].n_features_in_ if hasattr(general_model, 'estimators_') else general_model.n_features_in_
print(f"Model expects {n_feat_model} features | We provide {X_test.shape[1]}")
if n_feat_model != X_test.shape[1]:
    print(f"  WARNING: feature mismatch! Model trained on {n_feat_model}-feature vector.")
    print("  This means the saved model was trained without codon-bias features.")
    print("  Falling back: extracting 5446-feature vector (no codon block).")
    def extract_dna_features_nocodon(seq: str) -> list:
        seq = seq.upper().replace("U", "T")
        n = max(len(seq), 1)
        cnt = Counter(seq)
        total = sum(cnt.values())
        feats = [n,
            (cnt.get("G",0)+cnt.get("C",0))/n,
            (cnt.get("A",0)+cnt.get("T",0))/n,
            cnt.get("N",0)/n,
            max(cnt.values())/n if cnt else 0,
            -sum((c/total)*math.log2(c/total) for c in cnt.values() if c>0)]
        for k in [3,4,5,6]:
            kc = Counter(seq[i:i+k] for i in range(n-k+1))
            tk = max(n-k+1, 1)
            feats.extend(kc.get(km,0)/tk for km in VOCAB[k])
        return feats
    X_test = np.array([extract_dna_features_nocodon(s) for s in seqs_test])
    print(f"  Rebuilt features: shape={X_test.shape}")

# SynthGuard predictions (threshold = 0.5, consistent with paper benchmarks)
THRESH = 0.5
general_probs  = general_model.predict_proba(X_test)[:,1]
short_probs    = short_model.predict_proba(X_test)[:,1]

# Route by sequence length (same logic as API)
sg_probs = np.where(short_mask, short_probs, general_probs)
sg_preds = (sg_probs >= THRESH).astype(int)

print(f"\nSynthGuard predictions done. Threshold={THRESH}")
print(f"Overall predicted hazardous: {sg_preds.sum()} / {n_total}")


# ── CELL 11 ── Run real blastn on test set ────────────────────────────────────
#
# NOTE: This is the definitive cell. Each sequence is individually queried
# against the real blastn database. ~2,000–5,000 sequences × 0.1–0.5s each.
# On A100 (same box), expect 10–30 min total.

print("Running REAL blastn on test set...")
print("(This is not a proxy — each call is a real blastn subprocess)")
print()

blast_preds = []
t0 = time.time()
for i, seq in enumerate(seqs_test):
    is_short = len(seq) < 150
    hit = blastn_screen(seq, perc_identity=70.0, short=is_short)
    blast_preds.append(int(hit))
    if (i+1) % 200 == 0:
        elapsed = time.time() - t0
        eta = elapsed / (i+1) * (n_total - i - 1)
        print(f"  [{i+1}/{n_total}] elapsed={elapsed:.0f}s  ETA={eta:.0f}s  "
              f"flagged so far={sum(blast_preds)}")

blast_preds = np.array(blast_preds)
print(f"\nblastn done in {time.time()-t0:.1f}s")
print(f"Sequences flagged by blastn: {blast_preds.sum()} / {n_total}")

# Save raw predictions so you don't need to re-run
np.save("/content/blast_preds.npy", blast_preds)
np.save("/content/sg_probs.npy", sg_probs)
np.save("/content/sg_preds.npy", sg_preds)
print("Predictions saved to /content/")


# ── CELL 12 ── Run blastp on translatable sequences ───────────────────────────

print("Translating test sequences for blastp benchmark...")
prot_seqs  = []
prot_labels= []
prot_idx   = []   # index back into seqs_test
prot_source= []

for i, (seq, lbl, src) in enumerate(zip(seqs_test, labels_test, sources_test)):
    if len(seq) < 150:
        continue
    aa = translate_best_frame(seq)
    if len(aa) >= 30:
        prot_seqs.append(aa)
        prot_labels.append(lbl)
        prot_idx.append(i)
        prot_source.append(src)

print(f"Translatable sequences: {len(prot_seqs)}")

# Protein LightGBM predictions
X_prot = np.array([extract_protein_features(aa) for aa in prot_seqs])
prot_model_probs = protein_model.predict_proba(X_prot)[:,1]
prot_model_preds = (prot_model_probs >= THRESH).astype(int)

# Real blastp
print("\nRunning REAL blastp on translatable sequences...")
blastp_preds = []
t0 = time.time()
for i, aa in enumerate(prot_seqs):
    hit = blastp_screen(aa, perc_identity=50.0)  # 50% AA identity threshold
    blastp_preds.append(int(hit))
    if (i+1) % 100 == 0:
        elapsed = time.time() - t0
        eta = elapsed / (i+1) * (len(prot_seqs) - i - 1)
        print(f"  [{i+1}/{len(prot_seqs)}] elapsed={elapsed:.0f}s  ETA={eta:.0f}s")

blastp_preds = np.array(blastp_preds)
print(f"blastp done in {time.time()-t0:.1f}s")
np.save("/content/blastp_preds.npy", blastp_preds)


# ── CELL 13 ── Compute and display all metrics ────────────────────────────────

def metrics(labels, preds, probs=None):
    labels, preds = list(labels), list(preds)
    if len(set(labels)) < 2:
        return None
    cm = confusion_matrix(labels, preds)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2,2) else (0,0,0,0)
    auc = roc_auc_score(labels, probs) if probs is not None and len(set(labels))>1 else float("nan")
    return dict(
        recall   =recall_score(labels, preds, zero_division=0),
        precision=precision_score(labels, preds, zero_division=0),
        f1       =f1_score(labels, preds, zero_division=0),
        auroc    =auc,
        fpr      =fp/(fp+tn) if (fp+tn) else 0.0,
        tp=int(tp), fp=int(fp), tn=int(tn), fn=int(fn), n=len(labels),
    )

def row(m):
    if m is None: return "  (insufficient data)"
    return (f"  Recall={m['recall']:.3f}  Precision={m['precision']:.3f}  "
            f"F1={m['f1']:.3f}  AUROC={m['auroc']:.3f}  FPR={m['fpr']:.3f}  "
            f"n={m['n']}")

labels  = np.array(labels_test)
b_preds = blast_preds
s_preds = sg_preds
s_probs = sg_probs

print("\n" + "="*70)
print("FINAL BENCHMARK — Real blastn vs SynthGuard LightGBM")
print(f"blastn threshold: 70% identity | SynthGuard threshold: {THRESH}")
print("="*70)

slices = [
    ("Full test set",          np.ones(len(labels), dtype=bool)),
    ("Original sequences",     np.array([not any(t in str(s).lower()
                               for t in ["codon","shuffled","mpnn","variant",
                                         "fragment","redesign","augment"])
                               for s in sources_test])),
    ("Codon-shuffled variants",codon_mask),
    ("Fragment (<150bp)",      short_mask),
    ("ProteinMPNN DNA variants",mpnn_mask),
    ("Any AI-generated",       ai_mask),
]

results_table = {}
for name, mask in slices:
    if mask.sum() == 0 or len(set(labels[mask].tolist())) < 2:
        print(f"\n[{name}]  n={mask.sum()} — skipped (single class)")
        continue
    m_blast = metrics(labels[mask], b_preds[mask], b_preds[mask].astype(float))
    m_sg    = metrics(labels[mask], s_preds[mask], s_probs[mask])
    results_table[name] = {"blast": m_blast, "synthguard": m_sg}
    print(f"\n[{name}]  n={mask.sum()}  "
          f"({labels[mask].sum()} haz / {(1-labels[mask]).sum()} benign)")
    print(f"  blastn (70%):   {row(m_blast)}")
    print(f"  SynthGuard:     {row(m_sg)}")

# Protein slices
prot_labels_arr  = np.array(prot_labels)
prot_source_arr  = np.array(prot_source)
prot_mpnn_mask   = np.array([any(t in str(s).lower()
                               for t in ["mpnn","proteinmpnn","redesign","variant"])
                             for s in prot_source])
prot_codon_mask  = np.array([any(t in str(s).lower()
                               for t in ["codon","shuffled"])
                             for s in prot_source])

print("\n" + "-"*70)
print("PROTEIN TRACK — blastp (50% AA identity) vs Protein LightGBM")
print("-"*70)

prot_slices = [
    ("Protein — full translatable",  np.ones(len(prot_labels), dtype=bool)),
    ("Protein — ProteinMPNN variants",prot_mpnn_mask),
    ("Protein — codon-shuffled (AA)", prot_codon_mask),
]

for name, mask in prot_slices:
    if mask.sum() == 0 or len(set(prot_labels_arr[mask].tolist())) < 2:
        print(f"\n[{name}]  n={mask.sum()} — skipped")
        continue
    m_blastp = metrics(prot_labels_arr[mask], blastp_preds[mask],
                       blastp_preds[mask].astype(float))
    m_prot   = metrics(prot_labels_arr[mask], prot_model_preds[mask],
                       prot_model_probs[mask])
    results_table[name] = {"blastp": m_blastp, "protein_kmer": m_prot}
    print(f"\n[{name}]  n={mask.sum()}")
    print(f"  blastp (50%):        {row(m_blastp)}")
    print(f"  Protein k-mer LGB:   {row(m_prot)}")


# ── CELL 14 ── Summary table (paper format) ───────────────────────────────────

import pandas as pd

print("\n\n" + "="*70)
print("SUMMARY TABLE — for final paper")
print("="*70)

rows = []
for slice_name, d in results_table.items():
    for method_key, m in d.items():
        if m is None: continue
        rows.append({
            "Slice": slice_name,
            "Method": "blastn/blastp" if "blast" in method_key else "SynthGuard",
            "Recall": f"{m['recall']:.3f}",
            "Precision": f"{m['precision']:.3f}",
            "F1": f"{m['f1']:.3f}",
            "AUROC": f"{m['auroc']:.3f}" if not math.isnan(m['auroc']) else "—",
            "FPR": f"{m['fpr']:.3f}",
            "n": m['n'],
        })

df = pd.DataFrame(rows)
print(df.to_string(index=False))

# Save
df.to_csv("/content/benchmark_results.csv", index=False)
import json
with open("/content/benchmark_results.json", "w") as f:
    json.dump({k: {mk: {sk: float(sv) if isinstance(sv,(float,int)) else sv
                        for sk,sv in mv.items()}
                   for mk,mv in v.items()}
               for k,v in results_table.items()}, f, indent=2)
print("\nSaved: /content/benchmark_results.csv")
print("Saved: /content/benchmark_results.json")
print("\nDone. Download results and update the paper.")


# ── CELL 15 ── (Optional) Also log exact blastn version for the paper ─────────

result = subprocess.run(["blastn", "-version"], capture_output=True, text=True)
blastn_ver = result.stdout.strip().split("\n")[0]
result2 = subprocess.run(["blastp", "-version"], capture_output=True, text=True)
blastp_ver = result2.stdout.strip().split("\n")[0]

print("="*50)
print("VERSIONS (include in paper Methods section):")
print(f"  {blastn_ver}")
print(f"  {blastp_ver}")
print("="*50)

# Save version info alongside results
with open("/content/blast_version.txt", "w") as f:
    f.write(f"{blastn_ver}\n{blastp_ver}\n")
    f.write(f"DNA database: {len(original_haz_seqs)} original hazardous training sequences\n")
    f.write(f"Protein database: {len(original_haz_proteins)} translated protein sequences\n")
    f.write(f"blastn threshold: 70% identity\n")
    f.write(f"blastp threshold: 50% identity\n")
    f.write(f"SynthGuard classification threshold: {THRESH}\n")
