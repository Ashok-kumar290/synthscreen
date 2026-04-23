"""
SynthScreen Training Script
Dual-track biosecurity classifier:
  - Protein track: ESM-2 650M + LoRA — detects functional hazard from protein sequence
  - DNA track:    DNABERT-2 117M + LoRA — detects hazard directly from DNA (synthesis orders)

Key innovation over BLAST / SecureDNA / commec:
  Detects ProteinMPNN-designed functional analogs that are sequence-divergent from
  known hazards (the critical gap in current AI-era biosecurity screening).

Usage:
    # Protein track (ESM-2)
    python scripts/training/train_synthscreen.py --model_type esm2 \\
        --dataset_path data/processed/synthscreen_protein_v1_dataset \\
        --output_dir models/synthscreen_esm2

    # DNA track (DNABERT-2)
    python scripts/training/train_synthscreen.py --model_type dnabert2 \\
        --dataset_path data/processed/synthscreen_dna_v1_dataset \\
        --output_dir models/synthscreen_dnabert2
"""

import argparse
import json
import os
import sys
import random

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from datasets import load_from_disk, concatenate_datasets
from torch.utils.data import DataLoader
from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification, AutoConfig,
    TrainingArguments, Trainer, EarlyStoppingCallback
)
from peft import LoraConfig, get_peft_model, TaskType
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, precision_score, recall_score

DEFAULT_CONFIG = {
    "model_type": "dnabert2",
    "esm2_model_id": "facebook/esm2_t33_650M_UR50D",
    "dnabert2_model_id": "zhihan1996/DNABERT-2-117M",

    "dataset_path": "data/processed/synthscreen_dna_v1_dataset",
    "max_seq_length": 512,

    "lora_r": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.1,

    "epochs": 6,
    "batch_size": 16,
    "eval_batch_size": 32,
    "learning_rate": 2e-4,
    "weight_decay": 0.01,
    "warmup_ratio": 0.1,
    "lr_scheduler_type": "cosine",
    "fp16": True,
    "gradient_accumulation_steps": 2,

    "use_focal_loss": True,
    "focal_gamma": 2.0,
    "focal_alpha": None,
    "use_class_weights": True,

    "early_stopping_patience": 3,
    "early_stopping_threshold": 0.001,
    "max_grad_norm": 1.0,
    "label_smoothing": 0.05,

    "hard_mining_enabled": True,
    "hard_mining_rounds": 2,
    "hard_mining_threshold": 0.3,
    "hard_mining_oversample": 3,

    "output_dir": "models/synthscreen_v1",
    "logging_steps": 50,
    "max_train_val_gap": 0.10,
}


class FocalLoss(nn.Module):
    def __init__(self, gamma=2.0, alpha=None, class_weights=None, label_smoothing=0.0):
        super().__init__()
        self.gamma = gamma
        self.alpha = alpha
        self.class_weights = class_weights
        self.label_smoothing = label_smoothing

    def forward(self, logits, labels):
        if self.label_smoothing > 0:
            n_classes = logits.size(-1)
            smooth = torch.full_like(logits, self.label_smoothing / (n_classes - 1))
            smooth.scatter_(1, labels.unsqueeze(1), 1.0 - self.label_smoothing)
            ce_loss = -(smooth * F.log_softmax(logits, dim=-1)).sum(dim=-1)
        else:
            ce_loss = F.cross_entropy(logits, labels, weight=self.class_weights, reduction='none')
        p_t = F.softmax(logits, dim=-1).gather(1, labels.unsqueeze(1)).squeeze(1)
        focal_weight = (1 - p_t) ** self.gamma
        if self.alpha is not None:
            alpha_t = torch.where(labels == 1, self.alpha, 1 - self.alpha)
            focal_weight = alpha_t * focal_weight
        return (focal_weight * ce_loss).mean()


class SynthScreenTrainer(Trainer):
    def __init__(self, *args, focal_loss_fn=None, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.focal_loss_fn = focal_loss_fn
        self.config = config or {}

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits
        if logits.ndim == 3:
            logits = logits[:, 0, :]
        if logits.shape[-1] != 2:
            logits = logits[:, :2]
        loss = self.focal_loss_fn(logits, labels) if self.focal_loss_fn else F.cross_entropy(logits, labels)
        return (loss, outputs) if return_outputs else loss


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    if isinstance(logits, tuple):
        logits = logits[0]
    logits = np.array(logits)
    if logits.ndim == 3:
        logits = logits[:, 0, :]
    if logits.shape[-1] != 2:
        logits = logits[:, :2]
    probs = torch.softmax(torch.tensor(logits.copy()), dim=-1)[:, 1].numpy()
    preds = (probs > 0.5).astype(int)
    return {
        "accuracy": accuracy_score(labels, preds),
        "f1": f1_score(labels, preds, zero_division=0),
        "precision": precision_score(labels, preds, zero_division=0),
        "recall": recall_score(labels, preds, zero_division=0),
        "auroc": roc_auc_score(labels, probs) if len(set(labels)) > 1 else 0.5,
    }


def find_hard_examples(trainer, dataset, threshold):
    model = trainer.model
    model.eval()
    device = next(model.parameters()).device
    all_probs, all_labels = [], []

    with torch.no_grad():
        for batch in DataLoader(dataset, batch_size=8, shuffle=False):
            lbls = batch.pop("labels")
            inp = {k: v.to(device) for k, v in batch.items()}
            out = model(**inp)
            logits = out.logits
            if logits.ndim == 3:
                logits = logits[:, 0, :]
            if logits.shape[-1] != 2:
                logits = logits[:, :2]
            all_probs.append(torch.softmax(logits, dim=-1).cpu().numpy())
            all_labels.append(lbls.numpy())

    probs = np.concatenate(all_probs)
    labels = np.concatenate(all_labels)
    hard = [i for i in range(len(labels))
            if np.argmax(probs[i]) != labels[i] or probs[i][labels[i]] < (1 - threshold)]
    import gc; gc.collect(); torch.cuda.empty_cache()
    return hard, probs, labels


def build_model(config):
    model_type = config["model_type"]

    if model_type == "esm2":
        model_id = config["esm2_model_id"]
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        base = AutoModelForSequenceClassification.from_pretrained(model_id, num_labels=2)
        target_modules = ["query", "key", "value"]

    elif model_type == "dnabert2":
        model_id = config["dnabert2_model_id"]
        tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        cfg = AutoConfig.from_pretrained(model_id, num_labels=2, trust_remote_code=True)
        cfg.pad_token_id = tokenizer.pad_token_id or 0
        try:
            with torch.device("cpu"):
                base = AutoModelForSequenceClassification.from_pretrained(
                    model_id, config=cfg, trust_remote_code=True,
                    low_cpu_mem_usage=False, device_map=None
                )
        except Exception as e:
            print(f"  Primary load failed ({e}), using fallback...")
            base = AutoModelForSequenceClassification.from_pretrained(
                model_id, config=cfg, trust_remote_code=True
            )
        target_modules = ["Wqkv"]
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    lora_cfg = LoraConfig(
        r=config["lora_r"],
        lora_alpha=config["lora_alpha"],
        target_modules=target_modules,
        lora_dropout=config["lora_dropout"],
        bias="none",
        task_type=TaskType.SEQ_CLS,
        modules_to_save=["classifier"],
    )
    model = get_peft_model(base, lora_cfg)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Model: {model_id}")
    print(f"Trainable: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")
    return model, tokenizer, model_id


def tokenize_dataset(ds, tokenizer, max_length):
    seq_col = "sequence"
    remove_cols = [c for c in ds["train"].column_names if c not in ("label",)]

    def tok_fn(batch):
        return tokenizer(batch[seq_col], truncation=True, max_length=max_length, padding="max_length")

    tokenized = ds.map(tok_fn, batched=True, remove_columns=remove_cols)
    tokenized.set_format("torch")
    tokenized = tokenized.rename_column("label", "labels")
    return tokenized


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str)
    parser.add_argument("--model_type", choices=["esm2", "dnabert2"])
    parser.add_argument("--dataset_path", type=str)
    parser.add_argument("--output_dir", type=str)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--batch_size", type=int)
    parser.add_argument("--learning_rate", type=float)
    parser.add_argument("--lora_r", type=int)
    parser.add_argument("--max_seq_length", type=int)
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()
    if args.config:
        with open(args.config) as f:
            config.update(json.load(f))
    for key in ["model_type", "dataset_path", "output_dir", "epochs", "batch_size",
                "learning_rate", "lora_r", "max_seq_length"]:
        val = getattr(args, key, None)
        if val is not None:
            config[key] = val

    print(f"\n{'='*60}")
    print(f"SynthScreen Training — {config['model_type'].upper()}")
    print(f"{'='*60}")
    print(json.dumps({k: v for k, v in config.items() if not k.endswith("_id")}, indent=2))

    model, tokenizer, model_id = build_model(config)
    ds = load_from_disk(config["dataset_path"])
    tokenized = tokenize_dataset(ds, tokenizer, config["max_seq_length"])

    labels_arr = np.array(ds["train"]["label"])
    n_ben = (labels_arr == 0).sum()
    n_haz = (labels_arr == 1).sum()
    class_weights = torch.tensor(
        [len(labels_arr) / (2 * n_ben), len(labels_arr) / (2 * n_haz)],
        dtype=torch.float32
    ).to("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\nClass distribution: BEN={n_ben}, HAZ={n_haz}")

    focal_loss_fn = FocalLoss(
        gamma=config["focal_gamma"],
        class_weights=class_weights if config["use_class_weights"] else None,
        label_smoothing=config["label_smoothing"],
    ) if config["use_focal_loss"] else None

    training_args = TrainingArguments(
        output_dir=config["output_dir"],
        num_train_epochs=config["epochs"],
        per_device_train_batch_size=config["batch_size"],
        per_device_eval_batch_size=config["eval_batch_size"],
        learning_rate=config["learning_rate"],
        weight_decay=config["weight_decay"],
        warmup_ratio=config["warmup_ratio"],
        lr_scheduler_type=config["lr_scheduler_type"],
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        fp16=config["fp16"],
        logging_steps=config["logging_steps"],
        report_to="none",
        max_grad_norm=config["max_grad_norm"],
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
    )

    print(f"\n{'='*60}\nROUND 1: Initial Training\n{'='*60}")
    trainer = SynthScreenTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(
            early_stopping_patience=config["early_stopping_patience"],
            early_stopping_threshold=config["early_stopping_threshold"],
        )],
        focal_loss_fn=focal_loss_fn,
        config=config,
    )
    trainer.train()
    val_metrics = trainer.evaluate()
    print(f"\nRound 1 Validation: {json.dumps({k: round(v, 4) for k, v in val_metrics.items()}, indent=2)}")

    # Save after round 1
    save_dir = os.path.join(config["output_dir"], "peft_round1")
    os.makedirs(save_dir, exist_ok=True)
    state = {k: v.cpu() for k, v in model.state_dict().items()}
    torch.save(state, os.path.join(save_dir, "model_state_dict.pt"))

    # Hard example mining
    if config["hard_mining_enabled"]:
        for mining_round in range(1, config["hard_mining_rounds"] + 1):
            print(f"\n{'='*60}\nHARD MINING ROUND {mining_round}\n{'='*60}")
            hard_idx, _, _ = find_hard_examples(trainer, tokenized["train"], config["hard_mining_threshold"])
            print(f"Found {len(hard_idx)} hard examples ({100*len(hard_idx)/len(tokenized['train']):.1f}%)")
            if len(hard_idx) < 10:
                print("Too few hard examples, stopping mining.")
                break

            oversample_idx = hard_idx * config["hard_mining_oversample"]
            hard_ds = tokenized["train"].select(oversample_idx)
            augmented = concatenate_datasets([tokenized["train"], hard_ds]).shuffle(seed=42 + mining_round)
            print(f"Augmented set: {len(augmented)} examples")

            mining_args = TrainingArguments(
                output_dir=config["output_dir"] + f"_mining{mining_round}",
                num_train_epochs=max(1, config["epochs"] // 2),
                per_device_train_batch_size=config["batch_size"],
                per_device_eval_batch_size=config["eval_batch_size"],
                learning_rate=config["learning_rate"] * (0.5 ** mining_round),
                weight_decay=config["weight_decay"],
                warmup_ratio=config["warmup_ratio"],
                lr_scheduler_type=config["lr_scheduler_type"],
                eval_strategy="epoch",
                save_strategy="epoch",
                load_best_model_at_end=True,
                metric_for_best_model="f1",
                greater_is_better=True,
                fp16=config["fp16"],
                logging_steps=config["logging_steps"],
                report_to="none",
                max_grad_norm=config["max_grad_norm"],
            )
            trainer = SynthScreenTrainer(
                model=model,
                args=mining_args,
                train_dataset=augmented,
                eval_dataset=tokenized["validation"],
                compute_metrics=compute_metrics,
                focal_loss_fn=focal_loss_fn,
                config=config,
            )
            trainer.train()
            val_metrics = trainer.evaluate()
            print(f"Mining Round {mining_round}: {json.dumps({k: round(v, 4) for k, v in val_metrics.items()}, indent=2)}")

    # Final test evaluation
    print(f"\n{'='*60}\nFINAL TEST EVALUATION\n{'='*60}")
    test_out = trainer.predict(tokenized["test"])
    m = test_out.metrics
    print(f"Test Accuracy:  {m['test_accuracy']:.4f}")
    print(f"Test F1:        {m['test_f1']:.4f}")
    print(f"Test Precision: {m['test_precision']:.4f}")
    print(f"Test Recall:    {m['test_recall']:.4f}")
    print(f"Test AUROC:     {m['test_auroc']:.4f}")

    # Save final model
    final_dir = os.path.join(config["output_dir"], "peft_final")
    os.makedirs(final_dir, exist_ok=True)
    state = {k: v.cpu() for k, v in model.state_dict().items()}
    torch.save(state, os.path.join(final_dir, "model_state_dict.pt"))
    model.save_pretrained(os.path.join(config["output_dir"], "best"))

    results = {
        "config": config,
        "model_id": model_id,
        "test_metrics": {k.replace("test_", ""): round(v, 4) for k, v in m.items()},
    }
    with open(os.path.join(final_dir, "training_results.json"), "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"SynthScreen {config['model_type'].upper()} training complete!")
    print(f"Model saved to: {config['output_dir']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
