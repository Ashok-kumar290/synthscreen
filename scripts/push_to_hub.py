"""
Push all SynthGuard assets to HuggingFace Hub.

Usage:
    python scripts/push_to_hub.py --token hf_xxx
    python scripts/push_to_hub.py --token hf_xxx --skip_dataset
    python scripts/push_to_hub.py --token hf_xxx --skip_kmer --skip_esm2
"""

import argparse
import os
from pathlib import Path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", required=True)
    ap.add_argument("--dataset_repo", default="Seyomi/synthscreen-dataset")
    ap.add_argument("--kmer_repo",    default="Seyomi/synthguard-kmer")
    ap.add_argument("--esm2_repo",    default="Seyomi/synthguard-esm2")
    ap.add_argument("--dataset_path", default="data/processed/synthscreen_dna_v1_dataset")
    ap.add_argument("--kmer_path",    default="models/synthguard_kmer")
    ap.add_argument("--esm2_path",    default="models/synthguard_esm2")
    ap.add_argument("--skip_dataset", action="store_true")
    ap.add_argument("--skip_kmer",    action="store_true")
    ap.add_argument("--skip_esm2",    action="store_true")
    args = ap.parse_args()

    from huggingface_hub import HfApi, create_repo
    api = HfApi()

    # ── Dataset ───────────────────────────────────────────────────────────────
    if not args.skip_dataset:
        if Path(args.dataset_path).exists():
            print(f"Pushing dataset to {args.dataset_repo}...")
            from datasets import load_from_disk
            ds = load_from_disk(args.dataset_path)
            create_repo(args.dataset_repo, repo_type="dataset",
                        exist_ok=True, token=args.token)
            ds.push_to_hub(args.dataset_repo, token=args.token)
            print(f"  https://huggingface.co/datasets/{args.dataset_repo}")
        else:
            print(f"Dataset not found at {args.dataset_path}, skipping.")

    # ── K-mer models ──────────────────────────────────────────────────────────
    if not args.skip_kmer:
        if Path(args.kmer_path).exists():
            print(f"Pushing k-mer models to {args.kmer_repo}...")
            create_repo(args.kmer_repo, repo_type="model",
                        exist_ok=True, token=args.token)
            api.upload_folder(folder_path=args.kmer_path,
                              repo_id=args.kmer_repo,
                              repo_type="model", token=args.token)
            print(f"  https://huggingface.co/{args.kmer_repo}")
        else:
            print(f"K-mer models not found at {args.kmer_path}, skipping.")

    # ── ESM-2 ─────────────────────────────────────────────────────────────────
    if not args.skip_esm2:
        if Path(args.esm2_path).exists():
            print(f"Pushing ESM-2 to {args.esm2_repo}...")
            create_repo(args.esm2_repo, repo_type="model",
                        exist_ok=True, token=args.token)
            api.upload_folder(folder_path=args.esm2_path,
                              repo_id=args.esm2_repo,
                              repo_type="model", token=args.token)
            print(f"  https://huggingface.co/{args.esm2_repo}")
        else:
            print(f"ESM-2 not found at {args.esm2_path}, skipping.")

    print("\nAll done.")

if __name__ == "__main__":
    main()
