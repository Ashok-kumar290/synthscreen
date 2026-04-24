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

# ── k-mer features ────────────────────────────────────────────────────────────

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
        -sum((c/total)*math.log2(c/total) for c in cnt.values() if c > 0),
    ]
    for k in [3, 4, 5, 6]:
        kc = Counter(seq[i:i+k] for i in range(n-k+1))
        tk = max(n-k+1, 1)
        feats.extend(kc.get(km, 0)/tk for km in VOCAB[k])
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

    # ── BLAST proxy ───────────────────────────────────────────────────────────
    print("\n[BLAST proxy]")
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
        AA = {"TTT":"F","TTC":"F","TTA":"L","TTG":"L","CTT":"L","CTC":"L","CTA":"L","CTG":"L",
              "ATT":"I","ATC":"I","ATA":"I","ATG":"M","GTT":"V","GTC":"V","GTA":"V","GTG":"V",
              "GCT":"A","GCC":"A","GCA":"A","GCG":"A","TAT":"Y","TAC":"Y","CAT":"H","CAC":"H",
              "CAA":"Q","CAG":"Q","AAT":"N","AAC":"N","AAA":"K","AAG":"K","GAT":"D","GAC":"D",
              "GAA":"E","GAG":"E","TGT":"C","TGC":"C","TGG":"W","CGT":"R","CGC":"R","CGA":"R",
              "CGG":"R","AGA":"R","AGG":"R","AGT":"S","AGC":"S","TCT":"S","TCC":"S","TCA":"S",
              "TCG":"S","GGT":"G","GGC":"G","GGA":"G","GGG":"G","TAA":"*","TAG":"*","TGA":"*"}
        def translate(dna):
            return "".join(AA.get(dna[i:i+3], "X") for i in range(0, len(dna)-2, 3))

        # Use all translatable sequences (divisible by 3, no stop codons, min 15aa)
        prot_seqs, prot_lbls, prot_src = [], [], []
        for seq, lbl, src in zip(seqs, labels, sources):
            if len(seq) % 3 != 0:
                continue
            aa = translate(seq.upper())
            if len(aa) >= 15 and "*" not in aa and "X" not in aa:
                prot_seqs.append(aa)
                prot_lbls.append(lbl)
                prot_src.append(src)

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

    # ── Save models ───────────────────────────────────────────────────────────
    os.makedirs("models/synthguard_kmer", exist_ok=True)
    with open("models/synthguard_kmer/general_model.pkl", "wb") as f: pickle.dump(cal_g, f)
    with open("models/synthguard_kmer/short_model.pkl",   "wb") as f: pickle.dump(cal_s, f)
    feat_names = (["length","gc","at","n_frac","low_complex","entropy"] +
                  [f"k{k}_{km}" for k in [3,4,5,6] for km in VOCAB[k]])
    with open("models/synthguard_kmer/meta.json", "w") as f:
        json.dump({"n_features": len(feat_names), "feature_names": feat_names,
                   "short_threshold_bp": 150,
                   "decision_thresholds": {"review": 0.4, "escalate": 0.7}}, f, indent=2)
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
        ("blast_short",          "BLAST — Short (<150bp)"),
        ("dna_short",            "funcscreen DNABERT-2 — Short"),
        ("kmer_short_specialist","SynthGuard Short-Seq Specialist"),
        ("esm2_short",           "funcscreen ESM-2 — Short (<50aa)"),
        ("blast_ai",             "BLAST — AI Variants"),
        ("dna_ai",               "funcscreen DNABERT-2 — AI Variants"),
        ("kmer_ai",              "SynthGuard k-mer — AI Variants"),
        ("esm2_ai",              "funcscreen ESM-2 — AI Variants (protein)"),
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
