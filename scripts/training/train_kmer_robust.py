"""
FuncScreen — DNA K-mer + Random Forest Training
------------------------------------------------
Trains a K-mer frequency + Random Forest classifier for hazardous DNA detection.
Robust to codon shuffling and reverse-complement evasion.

Usage:
    python scripts/training/train_kmer_robust.py \
        --dataset data/processed/funcscreen_dna_v4_dataset \
        --output models/kmer_rf_v4 \
        --k 6
"""

import argparse
import json
import os

import joblib
import numpy as np
from datasets import DatasetDict, load_from_disk
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score


def train_kmer_model(dataset_path: str, output_dir: str, k: int = 6, n_estimators: int = 100):
    print(f"Loading dataset from {dataset_path}...")
    ds = load_from_disk(dataset_path)
    train_ds = ds["train"] if isinstance(ds, DatasetDict) else ds
    eval_ds = ds.get("validation") if isinstance(ds, DatasetDict) else None

    print(f"Vectorizing sequences with {k}-mer features...")
    vectorizer = CountVectorizer(analyzer="char", ngram_range=(k, k), lowercase=False)
    X_train = vectorizer.fit_transform(train_ds["sequence"])
    y_train = np.array(train_ds["label"])

    print(f"Training Random Forest ({n_estimators} trees)...")
    clf = RandomForestClassifier(n_estimators=n_estimators, n_jobs=-1, verbose=1)
    clf.fit(X_train, y_train)

    train_preds = clf.predict(X_train)
    print(f"Train Accuracy: {accuracy_score(y_train, train_preds):.4f}")
    print(f"Train F1:       {f1_score(y_train, train_preds):.4f}")

    if eval_ds is not None:
        X_val = vectorizer.transform(eval_ds["sequence"])
        y_val = np.array(eval_ds["label"])
        val_preds = clf.predict(X_val)
        val_proba = clf.predict_proba(X_val)[:, 1]
        print(f"Val Accuracy:   {accuracy_score(y_val, val_preds):.4f}")
        print(f"Val F1:         {f1_score(y_val, val_preds):.4f}")
        print(f"Val AUC-ROC:    {roc_auc_score(y_val, val_proba):.4f}")

    os.makedirs(output_dir, exist_ok=True)
    joblib.dump(clf, os.path.join(output_dir, "kmer_rf_model.pkl"))
    joblib.dump(vectorizer, os.path.join(output_dir, "vectorizer.pkl"))

    with open(os.path.join(output_dir, "vocab.json"), "w") as f:
        json.dump(vectorizer.vocabulary_, f)

    params = {
        "k": k,
        "ngram_range": [k, k],
        "analyzer": "char",
        "n_estimators": n_estimators,
        "dataset_path": dataset_path,
    }
    with open(os.path.join(output_dir, "params.json"), "w") as f:
        json.dump(params, f, indent=2)

    print(f"\n✅ DNA K-mer model saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train FuncScreen DNA K-mer Random Forest")
    parser.add_argument("--dataset", required=True, help="Path to HuggingFace dataset on disk")
    parser.add_argument("--output", required=True, help="Directory to save model artifacts")
    parser.add_argument("--k", type=int, default=6, help="K-mer size (default: 6)")
    parser.add_argument("--n_estimators", type=int, default=100, help="Number of RF trees (default: 100)")
    args = parser.parse_args()

    train_kmer_model(args.dataset, args.output, k=args.k, n_estimators=args.n_estimators)
