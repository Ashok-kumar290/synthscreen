"""
FuncScreen — ESM-2 LoRA Fine-tuning (with 8-bit quantization)
--------------------------------------------------------------
Fine-tunes ESM-2 650M with 8-bit QLoRA for binary hazard classification
on protein sequences.

Usage:
    python scripts/train_esm2.py \
        --dataset data/processed/funcscreen_protein_dataset \
        --output models/esm2_lora \
        --epochs 5 \
        --batch_size 8 \
        --lr 2e-4 \
        --lora_r 16 \
        --use_8bit
"""

import argparse
import os

import numpy as np
import torch
from datasets import load_from_disk
from peft import LoraConfig, TaskType, get_peft_model
from sklearn.metrics import f1_score, roc_auc_score
from transformers import (
    AutoTokenizer,
    BitsAndBytesConfig,
    EarlyStoppingCallback,
    EsmForSequenceClassification,
    Trainer,
    TrainingArguments,
)


MODEL_ID = "facebook/esm2_t33_650M_UR50D"
MODEL_ID_SMALL = "facebook/esm2_t30_150M_UR50D"  # fallback if OOM


def get_tokenizer(model_id: str):
    return AutoTokenizer.from_pretrained(model_id)


def tokenize_dataset(dataset, tokenizer, max_length: int = 512):
    def tokenize(batch):
        return tokenizer(
            batch["sequence"],
            padding="max_length",
            truncation=True,
            max_length=max_length,
        )
    return dataset.map(tokenize, batched=True, remove_columns=["sequence", "source", "id", "description", "length"])


def build_model(model_id: str, use_8bit: bool = True, lora_r: int = 16,
                lora_alpha: int = 32, lora_dropout: float = 0.1):
    load_kwargs = {"num_labels": 2}

    if use_8bit and torch.cuda.is_available():
        bnb_config = BitsAndBytesConfig(
            load_in_8bit=True,
            llm_int8_threshold=6.0,
        )
        load_kwargs["quantization_config"] = bnb_config
        load_kwargs["device_map"] = "auto"
        print("Loading ESM-2 with 8-bit quantization...")
    else:
        print("Loading ESM-2 without quantization (no GPU or 8-bit disabled)...")

    model = EsmForSequenceClassification.from_pretrained(model_id, **load_kwargs)

    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=["query", "key", "value"],
        lora_dropout=lora_dropout,
        bias="none",
        task_type=TaskType.SEQ_CLS,
        modules_to_save=["classifier"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    probs = torch.softmax(torch.tensor(logits, dtype=torch.float32), dim=-1)[:, 1].numpy()

    f1 = f1_score(labels, predictions, average="binary")
    try:
        auroc = roc_auc_score(labels, probs)
    except ValueError:
        auroc = 0.0
    accuracy = (predictions == labels).mean()

    return {"accuracy": accuracy, "f1": f1, "auroc": auroc}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", default="models/esm2_lora")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--max_length", type=int, default=512)
    parser.add_argument("--use_8bit", action="store_true", default=False)
    parser.add_argument("--use_small_model", action="store_true",
                        help="Use ESM-2 150M instead of 650M (fallback for OOM)")
    args = parser.parse_args()

    model_id = MODEL_ID_SMALL if args.use_small_model else MODEL_ID
    print(f"=== ESM-2 LoRA Fine-tuning ===")
    print(f"Model:   {model_id}")
    print(f"Dataset: {args.dataset}")
    print(f"Output:  {args.output}")

    dataset = load_from_disk(args.dataset)
    tokenizer = get_tokenizer(model_id)

    print("Tokenizing dataset...")
    tokenized = tokenize_dataset(dataset, tokenizer, max_length=args.max_length)

    try:
        model = build_model(model_id, use_8bit=args.use_8bit, lora_r=args.lora_r)
    except RuntimeError as e:
        if "out of memory" in str(e).lower() and not args.use_small_model:
            print("OOM with 650M model. Switching to ESM-2 150M fallback...")
            model_id = MODEL_ID_SMALL
            tokenizer = get_tokenizer(model_id)
            tokenized = tokenize_dataset(dataset, tokenizer, max_length=args.max_length)
            model = build_model(model_id, use_8bit=False, lora_r=args.lora_r)
        else:
            raise

    # Rename label → labels ONCE, after model is loaded successfully
    tokenized = tokenized.rename_column("label", "labels")

    os.makedirs(args.output, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        fp16=torch.cuda.is_available() and not args.use_8bit,
        logging_steps=50,
        report_to="none",
        dataloader_num_workers=2,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized["validation"],
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    print("Starting training...")
    trainer.train()

    best_path = os.path.join(args.output, "best")
    trainer.save_model(best_path)
    tokenizer.save_pretrained(best_path)
    print(f"\n✅ Best model saved to {best_path}")

    print("\nEvaluating on test set...")
    test_results = trainer.evaluate(tokenized["test"])
    print(test_results)


if __name__ == "__main__":
    main()
