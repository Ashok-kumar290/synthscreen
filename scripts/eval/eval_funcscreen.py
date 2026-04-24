"""
funcscreen-v4-robust Full Evaluation
Downloads both models from HuggingFace and runs benchmark vs BLAST.

Usage:
    python scripts/eval/eval_funcscreen.py \
        --dataset_path data/processed/synthscreen_dna_v1_dataset \
        --mpnn_variants data/mpnn_variants.json \
        --output_dir results/funcscreen_v4_eval
"""

import os, sys, json, argparse
import numpy as np
import torch
import torch.nn.functional as F
from datasets import load_from_disk
from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification, AutoConfig
)
from peft import LoraConfig, get_peft_model, TaskType
from huggingface_hub import hf_hub_download
from sklearn.metrics import (
    accuracy_score, f1_score, roc_auc_score,
    precision_score, recall_score, confusion_matrix
)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = "Seyomi/funcscreen-v4-robust"


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def screen_batch(seqs, model, tokenizer, device, max_len=512, batch_size=16):
    model.eval()
    all_probs = []
    for i in range(0, len(seqs), batch_size):
        batch = seqs[i:i + batch_size]
        enc = tokenizer(batch, return_tensors="pt", truncation=True,
                        max_length=max_len, padding=True)
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            logits = model(**enc).logits
            if logits.ndim == 3: logits = logits[:, 0, :]
            if logits.shape[-1] != 2: logits = logits[:, :2]
            probs = F.softmax(logits, dim=-1)[:, 1].cpu().numpy()
        all_probs.extend(probs.tolist())
    return np.array(all_probs)


def blast_proxy(seq, refs, k=7, thresh=0.70):
    sq = set(seq[i:i + k] for i in range(max(0, len(seq) - k + 1)))
    for r in refs:
        rk = set(r[i:i + k] for i in range(max(0, len(r) - k + 1)))
        if sq | rk and len(sq & rk) / len(sq | rk) >= thresh:
            return True
    return False


def compute_metrics(labels, preds, probs):
    labels = list(labels)
    preds  = list(preds)
    probs  = list(probs)
    acc = accuracy_score(labels, preds)
    f1  = f1_score(labels, preds, zero_division=0)
    pre = precision_score(labels, preds, zero_division=0)
    rec = recall_score(labels, preds, zero_division=0)
    auc = roc_auc_score(labels, probs) if len(set(labels)) > 1 else float("nan")
    cm  = confusion_matrix(labels, preds)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {"accuracy": acc, "f1": f1, "precision": pre,
            "recall": rec, "auroc": auc, "fpr": fpr,
            "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn)}


def print_metrics(name, m):
    print(f"\n{'─'*52}")
    print(f"  {name}")
    print(f"{'─'*52}")
    print(f"  Accuracy:  {m['accuracy']:.4f}")
    print(f"  F1:        {m['f1']:.4f}")
    print(f"  Precision: {m['precision']:.4f}")
    print(f"  Recall:    {m['recall']:.4f}")
    print(f"  AUROC:     {m['auroc']:.4f}")
    print(f"  FPR:       {m['fpr']:.4f}")
    print(f"  TP={m['tp']}  FP={m['fp']}  TN={m['tn']}  FN={m['fn']}")


def load_dna_model(device):
    print("\nLoading DNA model (DNABERT-2 + LoRA, 471MB)...")
    base_id = "zhihan1996/DNABERT-2-117M"
    tok = AutoTokenizer.from_pretrained(base_id, trust_remote_code=True)
    cfg = AutoConfig.from_pretrained(base_id, num_labels=2, trust_remote_code=True)
    cfg.pad_token_id = tok.pad_token_id or 0
    with torch.device("cpu"):
        base = AutoModelForSequenceClassification.from_pretrained(
            base_id, config=cfg, trust_remote_code=True,
            low_cpu_mem_usage=False, device_map=None
        )
    lora_cfg = LoraConfig(
        r=16, lora_alpha=32, target_modules=["Wqkv"],
        lora_dropout=0.1, bias="none",
        task_type=TaskType.SEQ_CLS, modules_to_save=["classifier"]
    )
    model = get_peft_model(base, lora_cfg)
    path = hf_hub_download(repo_id=REPO, filename="dna_robust/model_state_dict.pt")
    sd = torch.load(path, map_location="cpu")
    model.load_state_dict(sd, strict=False)
    model = model.to(device)
    model.eval()
    print(f"  DNA model ready on {device}")
    return model, tok


def load_protein_model(device):
    print("\nLoading protein model (ESM-2 650M + LoRA, 2.6GB — ~2min)...")
    base_id = "facebook/esm2_t33_650M_UR50D"
    tok = AutoTokenizer.from_pretrained(base_id)
    base = AutoModelForSequenceClassification.from_pretrained(base_id, num_labels=2)
    lora_cfg = LoraConfig(
        r=16, lora_alpha=32, target_modules=["query", "key", "value"],
        lora_dropout=0.1, bias="none",
        task_type=TaskType.SEQ_CLS, modules_to_save=["classifier"]
    )
    model = get_peft_model(base, lora_cfg)
    path = hf_hub_download(repo_id=REPO, filename="protein_hardened/model_state_dict.pt")
    sd = torch.load(path, map_location="cpu")
    model.load_state_dict(sd, strict=False)
    model = model.to(device)
    model.eval()
    print(f"  Protein model ready on {device}")
    return model, tok


def translate_dna(dna):
    aa_map = {
        "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
        "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
        "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
        "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
        "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
        "TAT": "Y", "TAC": "Y", "CAT": "H", "CAC": "H",
        "CAA": "Q", "CAG": "Q", "AAT": "N", "AAC": "N",
        "AAA": "K", "AAG": "K", "GAT": "D", "GAC": "D",
        "GAA": "E", "GAG": "E", "TGT": "C", "TGC": "C",
        "TGG": "W", "CGT": "R", "CGC": "R", "CGA": "R",
        "CGG": "R", "AGA": "R", "AGG": "R", "AGT": "S",
        "AGC": "S", "TCT": "S", "TCC": "S", "TCA": "S",
        "TCG": "S", "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
        "TAA": "*", "TAG": "*", "TGA": "*",
    }
    return "".join(aa_map.get(dna[i:i + 3], "X") for i in range(0, len(dna) - 2, 3))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset_path", default="data/processed/synthscreen_dna_v1_dataset")
    parser.add_argument("--mpnn_variants", default="data/mpnn_variants.json")
    parser.add_argument("--output_dir", default="results/funcscreen_v4_eval")
    parser.add_argument("--skip_protein", action="store_true", help="Skip ESM-2 eval (saves time)")
    args = parser.parse_args()

    device = get_device()
    print(f"{'='*60}\nfuncscreen-v4-robust Evaluation\n{'='*60}")
    print(f"Device: {device}")
    os.makedirs(args.output_dir, exist_ok=True)

    # ── Load test data ────────────────────────────────────────────
    print(f"\nLoading dataset from {args.dataset_path}...")
    ds = load_from_disk(args.dataset_path)
    test = ds["test"]
    dna_seqs = [x["sequence"] for x in test]
    labels   = [x["label"] for x in test]
    sources  = [x.get("source", "unknown") for x in test]

    print(f"Test set: {len(test)} sequences")
    print(f"  Hazardous: {sum(labels)}  Benign: {len(labels)-sum(labels)}")

    short_idx = [i for i, s in enumerate(dna_seqs) if len(s) < 150]
    ai_idx    = [i for i, s in enumerate(sources)
                 if any(x in s for x in ["codon", "shuffled", "variant"])]
    blast_refs = [dna_seqs[i] for i in range(len(labels)) if labels[i] == 1][:5]

    print(f"  Short (<150bp): {len(short_idx)}")
    print(f"  AI-variants:    {len(ai_idx)}")

    all_results = {}

    # ── DNA model evaluation ──────────────────────────────────────
    model_dna, tok_dna = load_dna_model(device)

    print("\nRunning DNA model inference...")
    dna_probs  = screen_batch(dna_seqs, model_dna, tok_dna, device)
    dna_preds  = (dna_probs >= 0.5).astype(int)
    blast_preds = np.array([int(blast_proxy(s, blast_refs)) for s in dna_seqs])

    m = compute_metrics(labels, dna_preds, dna_probs)
    print_metrics("SynthGuard DNA — Full Test Set", m)
    all_results["synthguard_dna_full"] = m

    m = compute_metrics(labels, blast_preds, blast_preds.astype(float))
    print_metrics("BLAST Proxy — Full Test Set", m)
    all_results["blast_full"] = m

    if short_idx:
        sl = [labels[i] for i in short_idx]
        m = compute_metrics(sl, dna_preds[short_idx], dna_probs[short_idx])
        print_metrics("SynthGuard DNA — Short Seqs (<150bp)", m)
        all_results["synthguard_dna_short"] = m

        m = compute_metrics(sl, blast_preds[short_idx], blast_preds[short_idx].astype(float))
        print_metrics("BLAST Proxy — Short Seqs (<150bp)", m)
        all_results["blast_short"] = m

    if ai_idx:
        al = [labels[i] for i in ai_idx]
        m = compute_metrics(al, dna_preds[ai_idx], dna_probs[ai_idx])
        print_metrics("SynthGuard DNA — AI-Designed Variants", m)
        all_results["synthguard_dna_ai"] = m

        m = compute_metrics(al, blast_preds[ai_idx], blast_preds[ai_idx].astype(float))
        print_metrics("BLAST — AI-Designed Variants", m)
        all_results["blast_ai"] = m

    # Free DNA model memory
    del model_dna
    torch.cuda.empty_cache() if torch.cuda.is_available() else None

    # ── Protein model evaluation ──────────────────────────────────
    if not args.skip_protein:
        prot_seqs, prot_labels = [], []

        if os.path.exists(args.mpnn_variants):
            with open(args.mpnn_variants) as f:
                mpnn = json.load(f)
            for e in mpnn.get("dangerous", []):
                ps = e.get("protein_sequence", "")
                if ps and len(ps) > 20:
                    prot_seqs.append(ps); prot_labels.append(1)
            for e in mpnn.get("benign", []):
                ps = e.get("protein_sequence", "")
                if ps and len(ps) > 20:
                    prot_seqs.append(ps); prot_labels.append(0)

        if len(prot_seqs) < 20:
            for seq, lbl in zip(dna_seqs[:120], labels[:120]):
                aa = translate_dna(seq)
                if len(aa) > 15 and "*" not in aa:
                    prot_seqs.append(aa); prot_labels.append(lbl)

        if prot_seqs:
            print(f"\nProtein eval set: {len(prot_seqs)} sequences")
            model_prot, tok_prot = load_protein_model(device)
            prot_probs = screen_batch(prot_seqs, model_prot, tok_prot, device)
            prot_preds = (prot_probs >= 0.5).astype(int)
            m = compute_metrics(prot_labels, prot_preds, prot_probs)
            print_metrics("SynthGuard Protein (ESM-2) — Test Set", m)
            all_results["synthguard_protein_full"] = m
            del model_prot
            torch.cuda.empty_cache() if torch.cuda.is_available() else None

    # ── Summary table ─────────────────────────────────────────────
    print(f"\n\n{'='*60}")
    print("FINAL SUMMARY — funcscreen-v4-robust")
    print(f"{'='*60}")
    print(f"  {'Model':<40} {'Recall':>7} {'FPR':>7} {'F1':>7} {'AUROC':>7}")
    print(f"  {'─'*56}")
    for key, m in all_results.items():
        name = key.replace("_", " ").title()
        print(f"  {name:<40} {m['recall']:>7.3f} {m['fpr']:>7.3f} "
              f"{m['f1']:>7.3f} {m['auroc']:>7.3f}")

    # Save JSON
    out_json = os.path.join(args.output_dir, "metrics.json")
    with open(out_json, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved: {out_json}")

    # ── Plot ──────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle("funcscreen-v4-robust: SynthGuard vs BLAST", fontsize=13)

    cats  = ["Full Set", "Short (<150bp)", "AI Variants"]
    our_r = [all_results.get("synthguard_dna_full",  {}).get("recall", 0),
              all_results.get("synthguard_dna_short", {}).get("recall", 0),
              all_results.get("synthguard_dna_ai",    {}).get("recall", 0)]
    bla_r = [all_results.get("blast_full",  {}).get("recall", 0),
              all_results.get("blast_short", {}).get("recall", 0),
              all_results.get("blast_ai",   {}).get("recall", 0)]

    x = np.arange(len(cats))
    axes[0].bar(x - 0.2, our_r, 0.35, label="SynthGuard (DNA)", color="#2ecc71")
    axes[0].bar(x + 0.2, bla_r, 0.35, label="BLAST proxy",      color="#e74c3c")
    axes[0].set_xticks(x); axes[0].set_xticklabels(cats, fontsize=9)
    axes[0].set_ylabel("Recall"); axes[0].set_ylim(0, 1.1)
    axes[0].set_title("Recall by Sequence Category"); axes[0].legend()
    for i, (o, b) in enumerate(zip(our_r, bla_r)):
        if o: axes[0].text(i - 0.2, o + 0.02, f"{o:.2f}", ha="center", fontsize=8)
        if b: axes[0].text(i + 0.2, b + 0.02, f"{b:.2f}", ha="center", fontsize=8)

    fpr_our = [all_results.get("synthguard_dna_full",  {}).get("fpr", 0),
               all_results.get("synthguard_dna_short", {}).get("fpr", 0)]
    fpr_bla = [all_results.get("blast_full",  {}).get("fpr", 0),
               all_results.get("blast_short", {}).get("fpr", 0)]
    x2 = np.arange(2)
    axes[1].bar(x2 - 0.2, fpr_our, 0.35, label="SynthGuard (DNA)", color="#2ecc71")
    axes[1].bar(x2 + 0.2, fpr_bla, 0.35, label="BLAST proxy",      color="#e74c3c")
    axes[1].set_xticks(x2); axes[1].set_xticklabels(["Full Set", "Short (<150bp)"])
    axes[1].set_ylabel("False Positive Rate (lower = better)")
    axes[1].set_ylim(0, 1.1); axes[1].set_title("False Positive Rate"); axes[1].legend()
    for i, (o, b) in enumerate(zip(fpr_our, fpr_bla)):
        if o: axes[1].text(i - 0.2, o + 0.02, f"{o:.2f}", ha="center", fontsize=8)
        if b: axes[1].text(i + 0.2, b + 0.02, f"{b:.2f}", ha="center", fontsize=8)

    plt.tight_layout()
    out_plot = os.path.join(args.output_dir, "benchmark_plot.png")
    plt.savefig(out_plot, dpi=150, bbox_inches="tight")
    print(f"Plot saved: {out_plot}")
    print(f"\n{'='*60}\nDone.\n{'='*60}")


if __name__ == "__main__":
    main()
