"""
SynthGuard full pipeline — terminal version of synthguard_full.ipynb

Usage:
    python scripts/run_pipeline.py \
        --dataset data/processed/synthscreen_dna_v1_dataset \
        --output  results/pipeline \
        --skip_protein        # optional: skip ESM-2 (saves 5 min + 2.6GB)
"""

import argparse, json, math, os, pickle, sys, warnings
warnings.filterwarnings("ignore")

import numpy as np
from collections import Counter
from itertools import product
from pathlib import Path

import torch
import torch.nn.functional as F

# ── Patch transformers auto_factory for DNABERT-2 compatibility ───────────────
# Newer transformers (>4.40) added a strict check that model_class.config_class
# must exactly match the config class. DNABERT-2's custom model inherits
# config_class=standard BertConfig but its config is a custom subclass → mismatch.
# Fix: temporarily align config_class during registration so the check passes.
def _patch_auto_factory():
    import transformers.models.auto.auto_factory as _af
    _orig = _af._BaseAutoModelClass.register.__func__

    @classmethod
    def _permissive_register(cls, config_class, model_class, exist_ok=False):
        old_cc = getattr(model_class, "config_class", None)
        if old_cc is not None and str(old_cc) != str(config_class):
            model_class.config_class = config_class
            try:
                _orig(cls, config_class, model_class, exist_ok=exist_ok)
            finally:
                model_class.config_class = old_cc
        else:
            _orig(cls, config_class, model_class, exist_ok=exist_ok)

    _af._BaseAutoModelClass.register = _permissive_register

_patch_auto_factory()


# ── Patch DNABERT-2 flash_attn_triton for new Triton API ─────────────────────
# Triton removed tl.dot(trans_b=True); replacement is tl.dot(a, tl.trans(b)).
# Patch the cached kernel file in-place so it compiles on any Triton version.
def _patch_flash_attn_triton():
    import glob, re, shutil
    for f in glob.glob('/root/.cache/huggingface/modules/transformers_modules/'
                       'zhihan1996/DNABERT-2-117M/*/flash_attn_triton.py'):
        text = open(f).read()
        if 'trans_b=True' not in text:
            continue
        text = re.sub(
            r'tl\.dot\(([^,]+),\s*([^,)]+),\s*trans_b=True',
            r'tl.dot(\1, tl.trans(\2)',
            text,
        )
        open(f, 'w').write(text)
        cache = os.path.expanduser('~/.triton/cache')
        if os.path.isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
        print(f'  flash_attn_triton.py patched (trans_b removed)')

_patch_flash_attn_triton()


from datasets import load_from_disk
from huggingface_hub import hf_hub_download
from peft import LoraConfig, get_peft_model, TaskType
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                              recall_score, roc_auc_score, confusion_matrix)
import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO   = "Seyomi/funcscreen-v4-robust"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ── helpers ───────────────────────────────────────────────────────────────────

def screen_batch(seqs, model, tokenizer, max_len=512, batch=16):
    model.eval()
    probs = []
    for i in range(0, len(seqs), batch):
        enc = tokenizer(seqs[i:i+batch], return_tensors="pt",
                        truncation=True, max_length=max_len, padding=True)
        enc = {k: v.to(DEVICE) for k, v in enc.items()}
        with torch.no_grad():
            logits = model(**enc).logits
            if logits.ndim == 3: logits = logits[:, 0, :]
            if logits.shape[-1] != 2: logits = logits[:, :2]
            probs.extend(F.softmax(logits, dim=-1)[:, 1].cpu().numpy().tolist())
    return np.array(probs)

def blast_proxy(seq, refs, k=7, thresh=0.70):
    sq = set(seq[i:i+k] for i in range(max(0, len(seq)-k+1)))
    for r in refs:
        rk = set(r[i:i+k] for i in range(max(0, len(r)-k+1)))
        if sq | rk and len(sq & rk) / len(sq | rk) >= thresh:
            return True
    return False


def blast_real(seq, db="hazard_db", thresh=70.0) -> bool:
    """Run actual blastn against local hazard database. Falls back to proxy if BLAST unavailable."""
    import subprocess, tempfile, os
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as f:
            f.write(f'>query\n{seq}\n')
            qfile = f.name
        result = subprocess.run(
            ["blastn", "-query", qfile, "-db", db,
             "-outfmt", "6 pident", "-max_hsps", "1", "-max_target_seqs", "1",
             "-perc_identity", str(thresh), "-dust", "no", "-task", "blastn-short"],
            capture_output=True, text=True, timeout=30
        )
        os.unlink(qfile)
        return bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def metrics(labels, preds, probs):
    labels, preds = list(labels), list(preds)
    cm = confusion_matrix(labels, preds)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)
    auc = roc_auc_score(labels, probs) if len(set(labels)) > 1 else float("nan")
    return dict(
        recall=recall_score(labels, preds, zero_division=0),
        precision=precision_score(labels, preds, zero_division=0),
        f1=f1_score(labels, preds, zero_division=0),
        auroc=auc,
        fpr=fp/(fp+tn) if (fp+tn) else 0.0,
        tp=int(tp), fp=int(fp), tn=int(tn), fn=int(fn),
    )

def show(name, m):
    print(f"\n  {'─'*50}\n  {name}\n  {'─'*50}")
    print(f"  Recall={m['recall']:.3f}  Precision={m['precision']:.3f}  "
          f"F1={m['f1']:.3f}  AUROC={m['auroc']:.3f}  FPR={m['fpr']:.3f}")
    print(f"  TP={m['tp']}  FP={m['fp']}  TN={m['tn']}  FN={m['fn']}")
    return m

# ── k-mer + codon-usage features ──────────────────────────────────────────────

VOCAB = {k: ["".join(p) for p in product("ACGT", repeat=k)] for k in [3, 4, 5, 6]}

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
    """RSCU (64) + CAI×3 (3) + AA composition (20) = 87 features."""
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
        if aa != '*': aa_cnt[aa] += n
    aa_feats = [aa_cnt.get(aa, 0) / max(aa_total, 1) for aa in AMINO_ACIDS]

    return rscu_feats + cai_feats + aa_feats

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
        -sum((c/total)*math.log2(c/total) for c in cnt.values() if c > 0),
    ]
    for k in [3, 4, 5, 6]:
        kc = Counter(seq[i:i+k] for i in range(n-k+1))
        tk = max(n-k+1, 1)
        feats.extend(kc.get(km, 0)/tk for km in VOCAB[k])
    feats.extend(_codon_features(seq))
    return feats

def build_X(seqs, desc=""):
    print(f"  Building features {desc}({len(seqs)} seqs)...", flush=True)
    return np.array([extract_features(s) for s in seqs])

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/processed/synthscreen_dna_v1_dataset")
    ap.add_argument("--output",  default="results/pipeline")
    ap.add_argument("--skip_protein", action="store_true")
    ap.add_argument("--skip_dna",     action="store_true")
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    ALL = {}

    # ── Load dataset ──────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("Loading dataset...")
    ds      = load_from_disk(args.dataset)
    test    = ds["test"]
    seqs    = [x["sequence"] for x in test]
    labels  = [x["label"]    for x in test]
    sources = [x.get("source", "original") for x in test]

    short_idx = [i for i, s in enumerate(seqs) if len(s) <  150]
    ai_idx    = [i for i, s in enumerate(sources)
                 if any(t in s for t in ["codon","shuffled","variant","fragment"])]
    refs      = [seqs[i] for i in range(len(labels)) if labels[i] == 1][:5]

    print(f"Test: {len(test)} seqs | hazardous={sum(labels)} | "
          f"short={len(short_idx)} | ai-variants={len(ai_idx)}")

    # ── BLAST (real blastn if available, else proxy) ───────────────────────────
    import shutil
    use_real_blast = shutil.which("blastn") is not None and os.path.exists("hazard_db.nhr")
    if use_real_blast:
        print("\n[BLAST — real blastn against hazard_db]")
        blast_p = np.array([int(blast_real(s)) for s in seqs])
    else:
        print("\n[BLAST proxy — k-mer Jaccard (blastn not found)]")
        blast_p = np.array([int(blast_proxy(s, refs)) for s in seqs])
    ALL["blast_full"] = show("BLAST — Full", metrics(labels, blast_p, blast_p.astype(float)))
    if short_idx:
        sl = [labels[i] for i in short_idx]
        ALL["blast_short"] = show("BLAST — Short (<150bp)",
            metrics(sl, blast_p[short_idx], blast_p[short_idx].astype(float)))
    if ai_idx:
        al = [labels[i] for i in ai_idx]
        ALL["blast_ai"] = show("BLAST — AI Variants",
            metrics(al, blast_p[ai_idx], blast_p[ai_idx].astype(float)))

    # ── DNABERT-2 ─────────────────────────────────────────────────────────────
    if args.skip_dna:
        print("\n[funcscreen DNABERT-2] SKIPPED (--skip_dna)")
    else:
        print("\n[funcscreen DNABERT-2]")
        from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoConfig

        base_id = "zhihan1996/DNABERT-2-117M"
        tok_dna = AutoTokenizer.from_pretrained(base_id, trust_remote_code=True)

        # Disable flash attention: DNABERT-2's bundled flash_attn_triton.py uses
        # tl.dot(trans_b=True) which was removed in newer Triton versions.
        # Setting use_flash_attn=False makes it fall back to standard attention.
        cfg = AutoConfig.from_pretrained(base_id, trust_remote_code=True)
        cfg.use_flash_attn = False
        cfg.num_labels = 2
        cfg.pad_token_id = tok_dna.pad_token_id if tok_dna.pad_token_id is not None else 0

        with torch.device("cpu"):
            base_dna = AutoModelForSequenceClassification.from_pretrained(
                base_id, config=cfg, trust_remote_code=True,
                low_cpu_mem_usage=False, device_map=None)

        lora_cfg = LoraConfig(r=16, lora_alpha=32, target_modules=["Wqkv"],
                              lora_dropout=0.1, bias="none",
                              task_type=TaskType.SEQ_CLS,
                              modules_to_save=["classifier"])
        model_dna = get_peft_model(base_dna, lora_cfg)
        sd = torch.load(hf_hub_download(REPO, "dna_robust/model_state_dict.pt"),
                        map_location="cpu")
        missing, unexpected = model_dna.load_state_dict(sd, strict=False)
        print(f"  Loaded — missing={len(missing)} unexpected={len(unexpected)}")
        model_dna = model_dna.to(DEVICE).eval()
        print("  Model loaded. Running inference...")

        dna_p  = screen_batch(seqs, model_dna, tok_dna)
        dna_pr = (dna_p >= 0.5).astype(int)
        ALL["dna_full"] = show("funcscreen DNA — Full", metrics(labels, dna_pr, dna_p))
        if short_idx:
            ALL["dna_short"] = show("funcscreen DNA — Short",
                metrics([labels[i] for i in short_idx], dna_pr[short_idx], dna_p[short_idx]))
        if ai_idx:
            ALL["dna_ai"] = show("funcscreen DNA — AI Variants",
                metrics([labels[i] for i in ai_idx], dna_pr[ai_idx], dna_p[ai_idx]))

        del model_dna; torch.cuda.empty_cache()

    # ── ESM-2 (optional) ──────────────────────────────────────────────────────
    if not args.skip_protein:
        print("\n[funcscreen ESM-2 650M]")
        from transformers import AutoTokenizer, AutoModelForSequenceClassification

        AA = {"TTT":"F","TTC":"F","TTA":"L","TTG":"L","CTT":"L","CTC":"L","CTA":"L","CTG":"L",
              "ATT":"I","ATC":"I","ATA":"I","ATG":"M","GTT":"V","GTC":"V","GTA":"V","GTG":"V",
              "GCT":"A","GCC":"A","GCA":"A","GCG":"A","TAT":"Y","TAC":"Y","CAT":"H","CAC":"H",
              "CAA":"Q","CAG":"Q","AAT":"N","AAC":"N","AAA":"K","AAG":"K","GAT":"D","GAC":"D",
              "GAA":"E","GAG":"E","TGT":"C","TGC":"C","TGG":"W","CGT":"R","CGC":"R","CGA":"R",
              "CGG":"R","AGA":"R","AGG":"R","AGT":"S","AGC":"S","TCT":"S","TCC":"S","TCA":"S",
              "TCG":"S","GGT":"G","GGC":"G","GGA":"G","GGG":"G","TAA":"*","TAG":"*","TGA":"*"}

        def translate_best_frame(dna):
            """Translate in all 3 frames, return longest ORF (truncated at first stop)."""
            dna = dna.upper()
            best = ""
            for frame in range(3):
                aa = "".join(AA.get(dna[i:i+3], "X")
                             for i in range(frame, len(dna)-2, 3))
                # Truncate at first stop codon
                if "*" in aa:
                    aa = aa[:aa.index("*")]
                if len(aa) > len(best):
                    best = aa
            return best

        # Keep only sequences >= 150bp (to get meaningful protein >= 50aa)
        # and that yield >= 30aa in best reading frame
        prot_seqs, prot_lbls, prot_src, prot_orig_idx = [], [], [], []
        for idx, (seq, lbl, src) in enumerate(zip(seqs, labels, sources)):
            if len(seq) < 150:
                continue
            aa = translate_best_frame(seq)
            if len(aa) >= 30:
                prot_seqs.append(aa)
                prot_lbls.append(lbl)
                prot_src.append(src)
                prot_orig_idx.append(idx)

        print(f"  Translatable sequences: {len(prot_seqs)} "
              f"({sum(prot_lbls)} hazardous / {len(prot_lbls)-sum(prot_lbls)} benign)")

        tok_p = AutoTokenizer.from_pretrained("facebook/esm2_t33_650M_UR50D")
        base_p = AutoModelForSequenceClassification.from_pretrained(
            "facebook/esm2_t33_650M_UR50D", num_labels=2)
        lora_p = LoraConfig(r=16, lora_alpha=32, target_modules=["query","key","value"],
                            lora_dropout=0.1, bias="none",
                            task_type=TaskType.SEQ_CLS, modules_to_save=["classifier"])
        model_p = get_peft_model(base_p, lora_p)
        sd_p = torch.load(hf_hub_download(REPO, "protein_hardened/model_state_dict.pt"),
                          map_location="cpu")
        model_p.load_state_dict(sd_p, strict=False)
        model_p = model_p.to(DEVICE).eval()
        print(f"  Running inference on {len(prot_seqs)} protein sequences...")
        prot_pr = screen_batch(prot_seqs, model_p, tok_p, batch=8)
        prot_pred = (prot_pr >= 0.5).astype(int)

        ALL["esm2_full"] = show("funcscreen ESM-2 — Full", metrics(prot_lbls, prot_pred, prot_pr))

        # Short protein slice
        short_prot = [i for i, s in enumerate(prot_seqs) if len(s) < 50]
        if short_prot and len(set(np.array(prot_lbls)[short_prot])) > 1:
            ALL["esm2_short"] = show("funcscreen ESM-2 — Short (<50aa)",
                metrics([prot_lbls[i] for i in short_prot],
                        prot_pred[short_prot], prot_pr[short_prot]))

        # AI-variant protein slice
        ai_prot = [i for i, s in enumerate(prot_src)
                   if any(t in s for t in ["codon","shuffled","variant","fragment"])]
        if ai_prot and len(set(np.array(prot_lbls)[ai_prot])) > 1:
            ALL["esm2_ai"] = show("funcscreen ESM-2 — AI Variants",
                metrics([prot_lbls[i] for i in ai_prot],
                        prot_pred[ai_prot], prot_pr[ai_prot]))

        del model_p; torch.cuda.empty_cache()

    # ── k-mer LightGBM ────────────────────────────────────────────────────────
    print("\n[SynthGuard k-mer LightGBM]")
    X_train = build_X([x["sequence"] for x in ds["train"]], "train ")
    y_train = np.array([x["label"] for x in ds["train"]])
    X_val   = build_X([x["sequence"] for x in ds["validation"]], "val ")
    y_val   = np.array([x["label"] for x in ds["validation"]])
    X_test  = build_X(seqs, "test ")
    y_test  = np.array(labels)

    print("  Training general model...")
    lgb_g = lgb.LGBMClassifier(n_estimators=500, max_depth=7, learning_rate=0.05,
                                 num_leaves=63, subsample=0.8, colsample_bytree=0.8,
                                 class_weight="balanced", random_state=42, verbose=-1)
    lgb_g.fit(X_train, y_train, eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(200)])
    cal_g = CalibratedClassifierCV(lgb_g, method="sigmoid", cv="prefit")
    cal_g.fit(X_val, y_val)

    gp = cal_g.predict_proba(X_test)[:, 1]
    ALL["kmer_full"] = show("SynthGuard k-mer — Full", metrics(labels, (gp>=0.5).astype(int), gp))
    if short_idx:
        sp2 = cal_g.predict_proba(X_test[short_idx])[:, 1]
        ALL["kmer_short_gen"] = show("SynthGuard k-mer — Short",
            metrics([labels[i] for i in short_idx], (sp2>=0.5).astype(int), sp2))
    if ai_idx:
        ap2 = cal_g.predict_proba(X_test[ai_idx])[:, 1]
        ALL["kmer_ai"] = show("SynthGuard k-mer — AI Variants",
            metrics([labels[i] for i in ai_idx], (ap2>=0.5).astype(int), ap2))

    print("\n  Training short-seq specialist...")
    short_train = [i for i, s in enumerate([x["sequence"] for x in ds["train"]]) if len(s) < 150]
    if len(short_train) >= 50:
        X_sh = X_train[short_train]; y_sh = y_train[short_train]
    else:
        frag_s, frag_l = [], []
        for s, l in zip([x["sequence"] for x in ds["train"]], y_train.tolist()):
            for st in range(0, len(s)-50, 50):
                f = s[st:st+np.random.randint(50, 150)]
                if len(f) >= 50: frag_s.append(f); frag_l.append(l)
        X_sh = build_X(frag_s, "short-aug "); y_sh = np.array(frag_l)
    short_val = [i for i, s in enumerate([x["sequence"] for x in ds["validation"]]) if len(s)<150]
    X_sv = X_val[short_val] if short_val else X_val
    y_sv = y_val[short_val] if short_val else y_val

    lgb_s = lgb.LGBMClassifier(n_estimators=400, max_depth=5, learning_rate=0.05,
                                 num_leaves=31, subsample=0.8, colsample_bytree=0.7,
                                 class_weight="balanced", random_state=42, verbose=-1)
    lgb_s.fit(X_sh, y_sh, eval_set=[(X_sv, y_sv)],
              callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(200)])
    cal_s = CalibratedClassifierCV(lgb_s, method="sigmoid", cv="prefit")
    cal_s.fit(X_sv, y_sv)

    if short_idx:
        ssp = cal_s.predict_proba(X_test[short_idx])[:, 1]
        ALL["kmer_short_specialist"] = show("SynthGuard Short-Seq Specialist",
            metrics([labels[i] for i in short_idx], (ssp>=0.5).astype(int), ssp))

    # ── Ensemble: k-mer + ESM-2 ───────────────────────────────────────────────
    if "esm2_full" in ALL and "prot_orig_idx" in dir() and prot_orig_idx:
        print("\n[SynthGuard Ensemble: k-mer + ESM-2]")
        prot_orig_idx = np.array(prot_orig_idx)
        ens_kmer  = gp[prot_orig_idx]
        ens_esm2  = prot_pr
        ens_scores = 0.6 * ens_kmer + 0.4 * ens_esm2
        ens_preds  = (ens_scores >= 0.5).astype(int)
        ALL["ensemble_full"] = show("SynthGuard Ensemble (k-mer+ESM-2) — Full",
            metrics(prot_lbls, ens_preds, ens_scores))
        ai_ens = [i for i, s in enumerate(prot_src)
                  if any(t in s for t in ["codon","shuffled","variant","fragment"])]
        if ai_ens and len(set(np.array(prot_lbls)[ai_ens])) > 1:
            ALL["ensemble_ai"] = show("SynthGuard Ensemble — AI Variants",
                metrics([prot_lbls[i] for i in ai_ens],
                        ens_preds[ai_ens], ens_scores[ai_ens]))

    # ── Save models ───────────────────────────────────────────────────────────
    os.makedirs("models/synthguard_kmer", exist_ok=True)
    with open("models/synthguard_kmer/general_model.pkl", "wb") as f: pickle.dump(cal_g, f)
    with open("models/synthguard_kmer/short_model.pkl",   "wb") as f: pickle.dump(cal_s, f)
    feat_names = (
        ["length","gc","at","n_frac","low_complex","entropy"] +
        [f"k{k}_{km}" for k in [3,4,5,6] for km in VOCAB[k]] +
        [f"rscu_{c}" for c in ALL_CODONS] +
        ["cai_ecoli","cai_human","cai_yeast"] +
        [f"aa_{a}" for a in AMINO_ACIDS]
    )
    with open("models/synthguard_kmer/meta.json", "w") as f:
        json.dump({"n_features": len(feat_names), "feature_names": feat_names,
                   "short_threshold_bp": 150,
                   "decision_thresholds": {"review": 0.4, "escalate": 0.7},
                   "feature_version": "v2_codon_norm"}, f, indent=2)
    print("\n  Models saved to models/synthguard_kmer/")

    # ── Final benchmark table ─────────────────────────────────────────────────
    print("\n\n" + "="*70)
    print("FINAL BENCHMARK — SynthGuard vs BLAST vs funcscreen-v4-robust")
    print("="*70)
    print(f"  {'Method':<40} {'Recall':>7} {'FPR':>7} {'F1':>7} {'AUROC':>7}")
    print("  " + "─"*64)
    rows = [
        ("blast_full",           "BLAST (70%) — Full"),
        ("dna_full",             "funcscreen DNABERT-2 — Full"),
        ("kmer_full",            "SynthGuard k-mer — Full"),
        ("esm2_full",            "funcscreen ESM-2 — Full (protein)"),
        ("ensemble_full",        "SynthGuard Ensemble (k-mer+ESM-2) — Full"),
        ("blast_short",          "BLAST — Short (<150bp)"),
        ("dna_short",            "funcscreen DNABERT-2 — Short"),
        ("kmer_short_specialist","SynthGuard Short-Seq Specialist"),
        ("esm2_short",           "funcscreen ESM-2 — Short (<50aa)"),
        ("blast_ai",             "BLAST — AI Variants"),
        ("dna_ai",               "funcscreen DNABERT-2 — AI Variants"),
        ("kmer_ai",              "SynthGuard k-mer — AI Variants"),
        ("esm2_ai",              "funcscreen ESM-2 — AI Variants (protein)"),
        ("ensemble_ai",          "SynthGuard Ensemble — AI Variants"),
    ]
    for key, label in rows:
        m = ALL.get(key)
        if not m: continue
        print(f"  {label:<40} {m['recall']:>7.3f} {m['fpr']:>7.3f} "
              f"{m['f1']:>7.3f} {m['auroc']:>7.3f}")

    print("\n\nKEY GAPS:")
    def pct(k, metric): return ALL.get(k, {}).get(metric, 0)
    print(f"  AI-variant recall:  BLAST={pct('blast_ai','recall'):.1%}  "
          f"DNABERT-2={pct('dna_ai','recall'):.1%}  "
          f"k-mer={pct('kmer_ai','recall'):.1%}")
    print(f"  Short-seq FPR:      BLAST={pct('blast_short','fpr'):.1%}  "
          f"DNABERT-2={pct('dna_short','fpr'):.1%}  "
          f"Specialist={pct('kmer_short_specialist','fpr'):.1%}")

    with open(os.path.join(args.output, "benchmark.json"), "w") as f:
        json.dump(ALL, f, indent=2)
    print(f"\nResults saved: {args.output}/benchmark.json")


if __name__ == "__main__":
    main()
