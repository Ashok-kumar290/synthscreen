"""
Run this in Colab to push updated model cards to HuggingFace.

!pip install -q huggingface_hub
import os; os.environ["HF_TOKEN"] = "your_token_here"  # or use userdata.get()
%run notebooks/push_model_cards_to_hf.py
"""

from huggingface_hub import HfApi
import os

api = HfApi()
token = os.environ.get("HF_TOKEN") or input("HF token: ")

# DNA + protein k-mer model card → Seyomi/synthguard-kmer
api.upload_file(
    path_or_fileobj="model_cards/kmer_README.md",
    path_in_repo="README.md",
    repo_id="Seyomi/synthguard-kmer",
    repo_type="model",
    token=token,
    commit_message="Update model card: verified April 26 2026 blastn/blastp benchmarks, correct 5533 features, real OOD results",
)
print("kmer README pushed to Seyomi/synthguard-kmer ✓")

# Protein V4 ESM-2 model card → Seyomi/synthguard-esm2
api.upload_file(
    path_or_fileobj="model_cards/esm2_README.md",
    path_in_repo="README.md",
    repo_id="Seyomi/synthguard-esm2",
    repo_type="model",
    token=token,
    commit_message="Update model card: rewritten for ESM-2 35M mean-pool + LightGBM V4, real blastp numbers",
)
print("esm2 README pushed to Seyomi/synthguard-esm2 ✓")
