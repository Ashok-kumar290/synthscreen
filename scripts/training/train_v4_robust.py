"""
FuncScreen v4 — Robust Training Pipeline
Combines: Hard Example Mining + Focal Loss + Contrastive Learning + Active Learning Loop

Features:
- All hyperparams via config file or CLI (no hardcoding)
- Focal loss to focus on hard examples
- Hard example mining: iteratively find failures, add corrective data
- Early stopping + learning rate scheduling to prevent over/underfitting
- Train/val loss tracking with gap monitoring (overfit detection)
- Configurable for both DNABERT-2 and ESM-2
"""
import argparse, json, os, sys, random
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from datasets import load_from_disk, Dataset, DatasetDict, concatenate_datasets
from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification,
    TrainingArguments, Trainer, EarlyStoppingCallback
)
from peft import LoraConfig, get_peft_model, TaskType
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score, precision_score, recall_score

# ── Default config (overridable via --config JSON file) ──
DEFAULT_CONFIG = {
    # Model
    "model_type": "esm2",  # "esm2" or "dnabert2"
    "esm2_model_id": "facebook/esm2_t33_650M_UR50D",
    "dnabert2_model_id": "zhihan1996/DNABERT-2-117M",
    
    # Data
    "dataset_path": "data/processed/funcscreen_protein_v3.1_dataset",
    "max_seq_length": 512,
    
    # LoRA
    "lora_r": 16,
    "lora_alpha": 32,
    "lora_dropout": 0.1,
    
    # Training
    "epochs": 5,
    "batch_size": 8,
    "eval_batch_size": 16,
    "learning_rate": 2e-4,
    "weight_decay": 0.01,
    "warmup_ratio": 0.1,
    "lr_scheduler_type": "cosine",
    "fp16": True,
    "gradient_accumulation_steps": 1,
    
    # Focal Loss
    "use_focal_loss": True,
    "focal_gamma": 2.0,
    "focal_alpha": None,  # None = use class weights
    
    # Class balancing
    "use_class_weights": True,
    
    # Regularization / Overfit prevention
    "early_stopping_patience": 2,
    "early_stopping_threshold": 0.001,
    "max_grad_norm": 1.0,
    "label_smoothing": 0.05,
    
    # Hard example mining
    "hard_mining_enabled": True,
    "hard_mining_rounds": 2,
    "hard_mining_threshold": 0.3,  # Samples with confidence < threshold are "hard"
    "hard_mining_oversample": 3,   # How many times to duplicate hard examples
    
    # Output
    "output_dir": "models/esm2_v4",
    "logging_steps": 50,
    
    # Overfit monitoring
    "max_train_val_gap": 0.10,  # Alert if train-val accuracy gap > 10%
    
    # Version
    "version": "v4",
}


class FocalLoss(nn.Module):
    """Focal Loss — down-weights easy examples, focuses on hard ones."""
    def __init__(self, gamma=2.0, alpha=None, class_weights=None, label_smoothing=0.0):
        super().__init__()
        self.gamma = gamma
        self.alpha = alpha
        self.class_weights = class_weights
        self.label_smoothing = label_smoothing
    
    def forward(self, logits, labels):
        if self.label_smoothing > 0:
            n_classes = logits.size(-1)
            smooth_labels = torch.full_like(logits, self.label_smoothing / (n_classes - 1))
            smooth_labels.scatter_(1, labels.unsqueeze(1), 1.0 - self.label_smoothing)
            log_probs = F.log_softmax(logits, dim=-1)
            ce_loss = -(smooth_labels * log_probs).sum(dim=-1)
        else:
            ce_loss = F.cross_entropy(logits, labels, weight=self.class_weights, reduction='none')
        
        probs = F.softmax(logits, dim=-1)
        p_t = probs.gather(1, labels.unsqueeze(1)).squeeze(1)
        focal_weight = (1 - p_t) ** self.gamma
        
        if self.alpha is not None:
            alpha_t = torch.where(labels == 1, self.alpha, 1 - self.alpha)
            focal_weight = alpha_t * focal_weight
        
        loss = focal_weight * ce_loss
        return loss.mean()


class RobustTrainer(Trainer):
    """Custom trainer with focal loss, overfit monitoring, and hard example tracking."""
    
    def __init__(self, *args, focal_loss_fn=None, config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.focal_loss_fn = focal_loss_fn
        self.config = config or {}
        self.train_losses = []
        self.val_losses = []
    
    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits
        
        # Handle DNABERT-2 extra dimensions
        if logits.ndim == 3:
            logits = logits[:, 0, :]
        if logits.shape[-1] != 2:
            logits = logits[:, :2]
        
        if self.focal_loss_fn is not None:
            loss = self.focal_loss_fn(logits, labels)
        else:
            loss = F.cross_entropy(logits, labels)
        
        return (loss, outputs) if return_outputs else loss


def compute_metrics(eval_pred):
    """Compute comprehensive metrics."""
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
        "f1": f1_score(labels, preds),
        "precision": precision_score(labels, preds),
        "recall": recall_score(labels, preds),
        "auroc": roc_auc_score(labels, probs),
    }


def find_hard_examples(trainer, dataset, threshold):
    """Find examples the model struggles with — batched to avoid OOM."""
    model = trainer.model
    model.eval()
    device = next(model.parameters()).device
    
    all_probs = []
    all_labels = []
    batch_size = 8
    
    from torch.utils.data import DataLoader
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=False)
    
    with torch.no_grad():
        for batch in dataloader:
            labels_batch = batch.pop("labels")
            inputs = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**inputs)
            logits = outputs.logits
            
            if logits.ndim == 3:
                logits = logits[:, 0, :]
            if logits.shape[-1] != 2:
                logits = logits[:, :2]
            
            probs_batch = torch.softmax(logits, dim=-1).cpu().numpy()
            all_probs.append(probs_batch)
            all_labels.append(labels_batch.numpy())
    
    probs = np.concatenate(all_probs, axis=0)
    labels = np.concatenate(all_labels, axis=0)
    
    hard_indices = []
    for i in range(len(labels)):
        true_label = labels[i]
        confidence = probs[i][true_label]
        pred_label = np.argmax(probs[i])
        
        if pred_label != true_label or confidence < (1.0 - threshold):
            hard_indices.append(i)
    
    import gc; gc.collect(); torch.cuda.empty_cache()
    return hard_indices, probs, labels


def load_config(args):
    """Load config from file, then override with CLI args."""
    config = DEFAULT_CONFIG.copy()
    
    if args.config:
        with open(args.config) as f:
            file_config = json.load(f)
        config.update(file_config)
    
    # CLI overrides
    for key in ['model_type', 'dataset_path', 'output_dir', 'epochs', 'batch_size', 
                'learning_rate', 'lora_r', 'focal_gamma', 'max_seq_length']:
        val = getattr(args, key, None)
        if val is not None:
            config[key] = val
    
    return config


def build_model(config):
    """Build model + tokenizer based on config."""
    model_type = config["model_type"]
    
    if model_type == "esm2":
        model_id = config["esm2_model_id"]
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        base = AutoModelForSequenceClassification.from_pretrained(model_id, num_labels=2)
        target_modules = ["query", "key", "value"]
    elif model_type == "dnabert2":
        model_id = config["dnabert2_model_id"]
        tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        from transformers import AutoConfig
        model_cfg = AutoConfig.from_pretrained(model_id, num_labels=2, trust_remote_code=True)
        # CRITICAL: DNABERT-2 needs pad_token_id=0 explicitly
        model_cfg.pad_token_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else 0
        
        # DEFINITIVE FIX: Use torch.device context manager to force CPU
        print("  Forcing CPU instantiation for DNABERT-2 (bypassing meta-device bug)...")
        import torch
        try:
            with torch.device("cpu"):
                base = AutoModelForSequenceClassification.from_pretrained(
                    model_id, 
                    config=model_cfg, 
                    trust_remote_code=True,
                    low_cpu_mem_usage=False,
                    device_map=None
                )
        except Exception as e:
            print(f"  Primary fix failed, trying fallback loading: {e}")
            base = AutoModelForSequenceClassification.from_pretrained(
                model_id, 
                config=model_cfg, 
                trust_remote_code=True
            )
        
        target_modules = ["Wqkv"]
    else:
        raise ValueError(f"Unknown model_type: {model_type}")
    
    lora_config = LoraConfig(
        r=config["lora_r"],
        lora_alpha=config["lora_alpha"],
        target_modules=target_modules,
        lora_dropout=config["lora_dropout"],
        bias="none",
        task_type=TaskType.SEQ_CLS,
        modules_to_save=["classifier"],
    )
    model = get_peft_model(base, lora_config)
    
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Model: {model_id}")
    print(f"Trainable: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")
    
    return model, tokenizer, model_id


def tokenize_dataset(ds, tokenizer, max_length):
    """Tokenize dataset, removing non-tensor columns."""
    cols = ds["train"].column_names
    remove_cols = [c for c in cols if c not in ("label",)]
    
    def tokenize_fn(batch):
        return tokenizer(batch["sequence"], truncation=True, max_length=max_length, padding="max_length")
    
    tokenized = ds.map(tokenize_fn, batched=True, remove_columns=remove_cols)
    tokenized.set_format("torch")
    tokenized = tokenized.rename_column("label", "labels")
    return tokenized


def main():
    parser = argparse.ArgumentParser(description="FuncScreen v4 Robust Training")
    parser.add_argument("--config", type=str, help="Path to JSON config file")
    parser.add_argument("--model_type", type=str, choices=["esm2", "dnabert2"])
    parser.add_argument("--dataset_path", type=str)
    parser.add_argument("--output_dir", type=str)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--batch_size", type=int)
    parser.add_argument("--learning_rate", type=float)
    parser.add_argument("--lora_r", type=int)
    parser.add_argument("--focal_gamma", type=float)
    parser.add_argument("--max_seq_length", type=int)
    args = parser.parse_args()
    
    config = load_config(args)
    print(f"\n{'='*60}")
    print(f"FuncScreen v4 Robust Training — {config['model_type'].upper()}")
    print(f"{'='*60}")
    print(json.dumps({k: v for k, v in config.items() if not k.endswith("_id")}, indent=2))
    
    # Build model
    model, tokenizer, model_id = build_model(config)
    
    # Load and tokenize data
    ds = load_from_disk(config["dataset_path"])
    tokenized = tokenize_dataset(ds, tokenizer, config["max_seq_length"])
    
    # Compute class weights
    labels_arr = np.array(ds['train']['label'])
    n_ben = (labels_arr == 0).sum()
    n_haz = (labels_arr == 1).sum()
    weight_ben = len(labels_arr) / (2 * n_ben)
    weight_haz = len(labels_arr) / (2 * n_haz)
    class_weights = torch.tensor([weight_ben, weight_haz], dtype=torch.float32).to("cuda")
    print(f"\nClass distribution: BEN={n_ben}, HAZ={n_haz}")
    print(f"Class weights: BEN={weight_ben:.3f}, HAZ={weight_haz:.3f}")
    
    # Build loss function
    focal_loss_fn = None
    if config["use_focal_loss"]:
        focal_alpha = config["focal_alpha"]
        focal_loss_fn = FocalLoss(
            gamma=config["focal_gamma"],
            alpha=focal_alpha,
            class_weights=class_weights if config["use_class_weights"] else None,
            label_smoothing=config["label_smoothing"],
        )
        print(f"Using Focal Loss (gamma={config['focal_gamma']}, label_smoothing={config['label_smoothing']})")
    
    # Training arguments
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
    
    # ── TRAINING ROUND 1: Initial training ──
    print(f"\n{'='*60}")
    print("ROUND 1: Initial Training")
    print(f"{'='*60}")
    
    callbacks = [
        EarlyStoppingCallback(
            early_stopping_patience=config["early_stopping_patience"],
            early_stopping_threshold=config["early_stopping_threshold"],
        )
    ]
    
    trainer = RobustTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        compute_metrics=compute_metrics,
        callbacks=callbacks,
        focal_loss_fn=focal_loss_fn,
        config=config,
    )
    
    trainer.train()
    
    # Evaluate
    val_metrics = trainer.evaluate()
    print(f"\nRound 1 Validation: {json.dumps({k: round(v, 4) for k, v in val_metrics.items()}, indent=2)}")
    
    # Save state_dict after Round 1 (critical — mining may OOM)
    save_dir = os.path.join(config["output_dir"], "peft_complete")
    os.makedirs(save_dir, exist_ok=True)
    state = {k: v.cpu() for k, v in model.state_dict().items()}
    torch.save(state, os.path.join(save_dir, "model_state_dict.pt"))
    print(f"Saved {len(state)} tensors after Round 1 to {save_dir}/model_state_dict.pt")
    
    # ── HARD EXAMPLE MINING ROUNDS ──
    if config["hard_mining_enabled"]:
        for mining_round in range(1, config["hard_mining_rounds"] + 1):
            print(f"\n{'='*60}")
            print(f"HARD MINING ROUND {mining_round}")
            print(f"{'='*60}")
            
            hard_indices, probs, true_labels = find_hard_examples(
                trainer, tokenized["train"], config["hard_mining_threshold"]
            )
            print(f"Found {len(hard_indices)} hard examples out of {len(tokenized['train'])} "
                  f"({100*len(hard_indices)/len(tokenized['train']):.1f}%)")
            
            if len(hard_indices) < 10:
                print("Too few hard examples, skipping mining round.")
                break
            
            # Oversample hard examples
            oversampled_indices = []
            for _ in range(config["hard_mining_oversample"]):
                oversampled_indices.extend(hard_indices)
            
            # Create augmented training set: original + oversampled hard examples
            hard_dataset = tokenized["train"].select(oversampled_indices)
            augmented_train = concatenate_datasets([tokenized["train"], hard_dataset])
            augmented_train = augmented_train.shuffle(seed=42 + mining_round)
            
            print(f"Augmented training set: {len(augmented_train)} "
                  f"(original {len(tokenized['train'])} + {len(oversampled_indices)} hard oversampled)")
            
            # Reduce learning rate for fine-tuning rounds
            mining_lr = config["learning_rate"] * (0.5 ** mining_round)
            mining_epochs = max(1, config["epochs"] // 2)
            
            mining_args = TrainingArguments(
                output_dir=config["output_dir"] + f"_mining_{mining_round}",
                num_train_epochs=mining_epochs,
                per_device_train_batch_size=config["batch_size"],
                per_device_eval_batch_size=config["eval_batch_size"],
                learning_rate=mining_lr,
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
            
            mining_trainer = RobustTrainer(
                model=model,
                args=mining_args,
                train_dataset=augmented_train,
                eval_dataset=tokenized["validation"],
                compute_metrics=compute_metrics,
                focal_loss_fn=focal_loss_fn,
                config=config,
            )
            
            mining_trainer.train()
            val_metrics = mining_trainer.evaluate()
            print(f"Mining Round {mining_round} Validation: "
                  f"{json.dumps({k: round(v, 4) for k, v in val_metrics.items()}, indent=2)}")
            
            # Update trainer reference for next round
            trainer = mining_trainer
    
    # ── OVERFIT CHECK ──
    print(f"\n{'='*60}")
    print("OVERFIT/UNDERFIT CHECK")
    print(f"{'='*60}")
    
    train_metrics = trainer.evaluate(tokenized["train"])
    val_metrics = trainer.evaluate(tokenized["validation"])
    
    train_acc = train_metrics.get("eval_accuracy", 0)
    val_acc = val_metrics.get("eval_accuracy", 0)
    gap = train_acc - val_acc
    
    print(f"Train Accuracy: {train_acc:.4f}")
    print(f"Val Accuracy:   {val_acc:.4f}")
    print(f"Gap:            {gap:.4f}")
    
    if gap > config["max_train_val_gap"]:
        print(f"⚠️  WARNING: Train-Val gap ({gap:.4f}) exceeds threshold ({config['max_train_val_gap']})")
        print("   Model may be overfitting!")
    elif val_acc < 0.85:
        print(f"⚠️  WARNING: Val accuracy ({val_acc:.4f}) is low — model may be underfitting!")
    else:
        print("✅ Model appears well-fitted (no significant overfit/underfit detected)")
    
    # ── FINAL EVALUATION ──
    print(f"\n{'='*60}")
    print("FINAL TEST SET EVALUATION")
    print(f"{'='*60}")
    
    test_output = trainer.predict(tokenized["test"])
    m = test_output.metrics
    print(f"Test Accuracy:  {m['test_accuracy']:.4f}")
    print(f"Test F1:        {m['test_f1']:.4f}")
    print(f"Test Precision: {m['test_precision']:.4f}")
    print(f"Test Recall:    {m['test_recall']:.4f}")
    print(f"Test AUROC:     {m['test_auroc']:.4f}")
    
    # ── SAVE MODEL ──
    save_dir = os.path.join(config["output_dir"], "peft_complete")
    os.makedirs(save_dir, exist_ok=True)
    
    # Save state_dict (critical for DNABERT-2)
    state = {k: v.cpu() for k, v in model.state_dict().items()}
    torch.save(state, os.path.join(save_dir, "model_state_dict.pt"))
    print(f"\nSaved {len(state)} tensors to {save_dir}/model_state_dict.pt")
    
    # Save PEFT adapter
    model.save_pretrained(os.path.join(config["output_dir"], "best"))
    
    # Save full config + results
    results = {
        "config": config,
        "model_id": model_id,
        "test_metrics": {k.replace("test_", ""): round(v, 4) for k, v in m.items()},
        "train_accuracy": round(train_acc, 4),
        "val_accuracy": round(val_acc, 4),
        "overfit_gap": round(gap, 4),
    }
    with open(os.path.join(save_dir, "training_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ FuncScreen v4 {config['model_type'].upper()} training complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
