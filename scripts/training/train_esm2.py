"""
ESM-2 650M LoRA fine-tuning — SynthGuard protein track.

Fixes the funcscreen-v4-robust checkpoint problem (classifier head was never saved).
Trains from scratch on our dataset with focal loss + hard example mining.

Usage:
    python scripts/training/train_esm2.py \
        --dataset data/processed/synthscreen_dna_v1_dataset \
        --output  models/synthguard_esm2 \
        --push_to_hub Seyomi/synthguard-esm2 \
        --hf_token hf_xxx \
        --epochs 3
"""

import argparse
import json
import os
import warnings

import numpy as np
import torch
import torch.nn.functional as F
from datasets import load_from_disk
from peft import LoraConfig, TaskType, get_peft_model
from sklearn.metrics import (f1_score, precision_score, recall_score,
                             roc_auc_score)
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from transformers import AutoModelForSequenceClassification, AutoTokenizer

warnings.filterwarnings("ignore")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

AA_TABLE = {
    "TTT":"F","TTC":"F","TTA":"L","TTG":"L","CTT":"L","CTC":"L","CTA":"L","CTG":"L",
    "ATT":"I","ATC":"I","ATA":"I","ATG":"M","GTT":"V","GTC":"V","GTA":"V","GTG":"V",
    "GCT":"A","GCC":"A","GCA":"A","GCG":"A","TAT":"Y","TAC":"Y","CAT":"H","CAC":"H",
    "CAA":"Q","CAG":"Q","AAT":"N","AAC":"N","AAA":"K","AAG":"K","GAT":"D","GAC":"D",
    "GAA":"E","GAG":"E","TGT":"C","TGC":"C","TGG":"W","CGT":"R","CGC":"R","CGA":"R",
    "CGG":"R","AGA":"R","AGG":"R","AGT":"S","AGC":"S","TCT":"S","TCC":"S","TCA":"S",
    "TCG":"S","GGT":"G","GGC":"G","GGA":"G","GGG":"G","TAA":"*","TAG":"*","TGA":"*",
}


def translate_best_frame(dna: str) -> str:
    dna = dna.upper()
    best = ""
    for frame in range(3):
        aa = "".join(AA_TABLE.get(dna[i:i+3], "X")
                     for i in range(frame, len(dna)-2, 3))
        if "*" in aa:
            aa = aa[:aa.index("*")]
        if len(aa) > len(best):
            best = aa
    return best


def get_protein_items(split, min_aa: int = 30):
    items = []
    for ex in split:
        seq = ex["sequence"]
        if len(seq) < 90:
            continue
        aa = translate_best_frame(seq)
        if len(aa) >= min_aa:
            items.append({
                "sequence": aa,
                "label": ex["label"],
                "source": ex.get("source", "original"),
            })
    return items


class ProteinDataset(Dataset):
    def __init__(self, items, tokenizer, max_len=512):
        self.items = items
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        return len(self.items)

    def __getitem__(self, idx):
        item = self.items[idx]
        enc = self.tokenizer(
            item["sequence"],
            truncation=True,
            max_length=self.max_len,
            padding="max_length",
            return_tensors="pt",
        )
        return {
            "input_ids":      enc["input_ids"].squeeze(0),
            "attention_mask": enc["attention_mask"].squeeze(0),
            "labels":         torch.tensor(item["label"], dtype=torch.long),
        }


def focal_loss(logits, labels, gamma=2.0, alpha=0.75):
    ce    = F.cross_entropy(logits, labels, reduction="none")
    pt    = torch.exp(-ce)
    alpha_t = torch.where(
        labels == 1,
        torch.tensor(alpha,   device=logits.device),
        torch.tensor(1-alpha, device=logits.device),
    )
    return (alpha_t * (1 - pt) ** gamma * ce).mean()


@torch.no_grad()
def evaluate(model, loader):
    model.eval()
    all_labels, all_preds, all_probs = [], [], []
    total_loss = 0.0
    for batch in loader:
        ids   = batch["input_ids"].to(DEVICE)
        mask  = batch["attention_mask"].to(DEVICE)
        lbls  = batch["labels"].to(DEVICE)
        logits = model(input_ids=ids, attention_mask=mask).logits
        total_loss += focal_loss(logits, lbls).item()
        probs = F.softmax(logits, dim=-1)[:, 1].cpu().numpy()
        all_labels.extend(lbls.cpu().numpy().tolist())
        all_preds.extend((probs >= 0.5).astype(int).tolist())
        all_probs.extend(probs.tolist())

    auc = roc_auc_score(all_labels, all_probs) if len(set(all_labels)) > 1 else 0.5
    return {
        "loss":      round(total_loss / max(len(loader), 1), 4),
        "f1":        round(f1_score(all_labels, all_preds, zero_division=0), 4),
        "recall":    round(recall_score(all_labels, all_preds, zero_division=0), 4),
        "precision": round(precision_score(all_labels, all_preds, zero_division=0), 4),
        "auroc":     round(auc, 4),
        "fpr":       round(
            sum(p==1 and l==0 for p,l in zip(all_preds,all_labels)) /
            max(sum(l==0 for l in all_labels), 1), 4),
    }


def make_loader(items, tokenizer, max_len, batch_size, balanced=True, shuffle=True):
    ds = ProteinDataset(items, tokenizer, max_len)
    if balanced:
        lbls = [x["label"] for x in items]
        counts = [lbls.count(0), lbls.count(1)]
        weights = [1.0 / counts[l] for l in lbls]
        sampler = WeightedRandomSampler(weights, len(weights), replacement=True)
        return DataLoader(ds, batch_size=batch_size, sampler=sampler)
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset",       default="data/processed/synthscreen_dna_v1_dataset")
    ap.add_argument("--output",        default="models/synthguard_esm2")
    ap.add_argument("--push_to_hub",   default=None)
    ap.add_argument("--hf_token",      default=None)
    ap.add_argument("--epochs",        type=int,   default=3)
    ap.add_argument("--batch_size",    type=int,   default=8)
    ap.add_argument("--lr",            type=float, default=2e-4)
    ap.add_argument("--max_len",       type=int,   default=512)
    ap.add_argument("--lora_r",        type=int,   default=16)
    ap.add_argument("--lora_alpha",    type=int,   default=32)
    ap.add_argument("--mining_rounds", type=int,   default=2)
    ap.add_argument("--resume",        action="store_true",
                    help="Auto-resume from latest epoch checkpoint in output dir")
    args = ap.parse_args()

    os.makedirs(args.output, exist_ok=True)
    print("=" * 65)
    print("ESM-2 650M Fine-Tuning — SynthGuard Protein Track")
    print(f"Device: {DEVICE}  |  Epochs: {args.epochs}  |  LR: {args.lr}")
    print("=" * 65)

    # ── Dataset ───────────────────────────────────────────────────────────────
    print("\n[1/5] Loading and translating dataset...")
    ds = load_from_disk(args.dataset)
    train_items = get_protein_items(ds["train"])
    val_items   = get_protein_items(ds["validation"])
    test_items  = get_protein_items(ds["test"])
    print(f"  Train: {len(train_items)} "
          f"({sum(x['label'] for x in train_items)} haz / "
          f"{sum(1-x['label'] for x in train_items)} benign)")
    print(f"  Val:   {len(val_items)} "
          f"({sum(x['label'] for x in val_items)} haz)")
    print(f"  Test:  {len(test_items)} "
          f"({sum(x['label'] for x in test_items)} haz)")

    # ── Model ─────────────────────────────────────────────────────────────────
    print("\n[2/5] Loading ESM-2 650M + LoRA...")
    base_id   = "facebook/esm2_t33_650M_UR50D"
    tokenizer = AutoTokenizer.from_pretrained(base_id)
    base      = AutoModelForSequenceClassification.from_pretrained(
        base_id, num_labels=2, ignore_mismatched_sizes=True)

    lora_cfg = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha,
        target_modules=["query", "key", "value"],
        lora_dropout=0.1, bias="none",
        task_type=TaskType.SEQ_CLS,
        modules_to_save=["classifier"],
    )
    model = get_peft_model(base, lora_cfg).to(DEVICE)
    model.print_trainable_parameters()

    val_loader  = make_loader(val_items,  tokenizer, args.max_len, args.batch_size,
                              balanced=False, shuffle=False)
    test_loader = make_loader(test_items, tokenizer, args.max_len, args.batch_size,
                              balanced=False, shuffle=False)

    # ── Training ──────────────────────────────────────────────────────────────
    print(f"\n[3/5] Training {args.epochs} epochs...")
    optimizer   = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=args.lr, weight_decay=0.01)
    best_val_f1 = 0.0
    best_state  = None
    current_train = train_items.copy()

    # Auto-resume from latest checkpoint
    start_epoch = 1
    if args.resume:
        ckpts = sorted([
            d for d in os.listdir(args.output)
            if d.startswith("checkpoint_epoch_")
        ])
        if ckpts:
            latest = os.path.join(args.output, ckpts[-1], "model_state_dict.pt")
            meta_path = os.path.join(args.output, ckpts[-1], "meta.json")
            if os.path.exists(latest):
                print(f"  Resuming from {ckpts[-1]}...")
                model.load_state_dict(torch.load(latest, map_location=DEVICE))
                if os.path.exists(meta_path):
                    with open(meta_path) as f:
                        ckpt_meta = json.load(f)
                    best_val_f1 = ckpt_meta.get("val_f1", 0.0)
                    start_epoch = ckpt_meta.get("epoch", 0) + 1
                print(f"  Resumed at epoch {start_epoch}, best val F1 so far: {best_val_f1:.3f}")

    for epoch in range(start_epoch, args.epochs + 1):
        train_loader = make_loader(current_train, tokenizer, args.max_len,
                                   args.batch_size, balanced=True)
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer, max_lr=args.lr,
            steps_per_epoch=len(train_loader), epochs=1, pct_start=0.1)

        model.train()
        running_loss = 0.0
        for step, batch in enumerate(train_loader, 1):
            ids   = batch["input_ids"].to(DEVICE)
            mask  = batch["attention_mask"].to(DEVICE)
            lbls  = batch["labels"].to(DEVICE)
            optimizer.zero_grad()
            loss = focal_loss(model(input_ids=ids, attention_mask=mask).logits, lbls)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            running_loss += loss.item()
            if step % 100 == 0:
                print(f"  Epoch {epoch} step {step}/{len(train_loader)}  "
                      f"loss={running_loss/step:.4f}", flush=True)

        val_m = evaluate(model, val_loader)
        print(f"\n  Epoch {epoch} — val_F1={val_m['f1']:.3f}  "
              f"val_recall={val_m['recall']:.3f}  val_AUROC={val_m['auroc']:.3f}  "
              f"val_FPR={val_m['fpr']:.3f}")

        if val_m["f1"] > best_val_f1:
            best_val_f1 = val_m["f1"]
            best_state  = {k: v.clone() for k, v in model.state_dict().items()}
            print(f"  ✓ New best val F1: {best_val_f1:.3f}")

        # Save epoch checkpoint (so disconnect doesn't lose all progress)
        ckpt_dir = os.path.join(args.output, f"checkpoint_epoch_{epoch}")
        os.makedirs(ckpt_dir, exist_ok=True)
        torch.save(model.state_dict(), os.path.join(ckpt_dir, "model_state_dict.pt"))
        with open(os.path.join(ckpt_dir, "meta.json"), "w") as f:
            json.dump({"epoch": epoch, "val_f1": val_m["f1"],
                       "val_metrics": val_m}, f, indent=2)
        print(f"  Checkpoint saved: {ckpt_dir}")

        # Hard example mining
        if epoch <= args.mining_rounds and epoch < args.epochs:
            print(f"  Mining hard examples (epoch {epoch})...")
            model.eval()
            mining_loader = make_loader(train_items, tokenizer, args.max_len,
                                        args.batch_size, balanced=False, shuffle=False)
            hard = []
            idx = 0
            with torch.no_grad():
                for batch in mining_loader:
                    bs    = batch["input_ids"].shape[0]
                    probs = F.softmax(
                        model(input_ids=batch["input_ids"].to(DEVICE),
                              attention_mask=batch["attention_mask"].to(DEVICE)).logits,
                        dim=-1)[:, 1].cpu().numpy()
                    lbls_b = batch["labels"].numpy()
                    for i in range(bs):
                        # False negatives + uncertain positives
                        if lbls_b[i] == 1 and probs[i] < 0.6:
                            hard.append(train_items[idx + i])
                    idx += bs
            current_train = train_items + hard
            print(f"  {len(hard)} hard examples added → {len(current_train)} total")

    # ── Final test evaluation ─────────────────────────────────────────────────
    print("\n[4/5] Final evaluation on test set...")
    model.load_state_dict(best_state)
    test_m = evaluate(model, test_loader)
    print(f"  Full test — Recall={test_m['recall']:.3f}  FPR={test_m['fpr']:.3f}  "
          f"F1={test_m['f1']:.3f}  AUROC={test_m['auroc']:.3f}")

    slice_results = {}
    for name, items in [
        ("AI variants",   [x for x in test_items if any(
            t in x["source"] for t in ["codon","shuffled","variant","fragment"])]),
        ("Short (<50aa)", [x for x in test_items if len(x["sequence"]) < 50]),
    ]:
        if len(items) < 10 or len(set(x["label"] for x in items)) < 2:
            continue
        sl = make_loader(items, tokenizer, args.max_len, args.batch_size,
                         balanced=False, shuffle=False)
        m = evaluate(model, sl)
        print(f"  {name} — Recall={m['recall']:.3f}  F1={m['f1']:.3f}  "
              f"AUROC={m['auroc']:.3f}")
        slice_results[name] = m

    # ── Save ──────────────────────────────────────────────────────────────────
    print("\n[5/5] Saving...")

    # Full state dict (LoRA adapters + classifier)
    torch.save(model.state_dict(),
               os.path.join(args.output, "model_state_dict.pt"))

    # Merged weights (LoRA baked in — easy inference, no PEFT dependency)
    merged = model.merge_and_unload()
    merged.save_pretrained(os.path.join(args.output, "merged"))
    tokenizer.save_pretrained(os.path.join(args.output, "merged"))
    print(f"  Merged model saved to {args.output}/merged/")

    meta = {
        "base_model": base_id,
        "lora_r": args.lora_r, "lora_alpha": args.lora_alpha,
        "epochs": args.epochs, "best_val_f1": best_val_f1,
        "test_metrics": test_m, "slice_metrics": slice_results,
        "translation": "best_reading_frame_of_3", "min_protein_aa": 30,
    }
    with open(os.path.join(args.output, "training_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Metadata saved.")

    # ── Push to HF ────────────────────────────────────────────────────────────
    if args.push_to_hub and args.hf_token:
        print(f"\nPushing to HuggingFace: {args.push_to_hub}...")
        from huggingface_hub import HfApi, create_repo
        api = HfApi()
        create_repo(args.push_to_hub, repo_type="model",
                    exist_ok=True, token=args.hf_token)
        api.upload_folder(
            folder_path=args.output,
            repo_id=args.push_to_hub,
            repo_type="model",
            token=args.hf_token,
        )
        print(f"  https://huggingface.co/{args.push_to_hub}")

    print("\nDone.")
    print(f"\nSummary: Test F1={test_m['f1']:.3f}  "
          f"Recall={test_m['recall']:.3f}  AUROC={test_m['auroc']:.3f}")


if __name__ == "__main__":
    main()
