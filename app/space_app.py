"""
HuggingFace Space entry point for SynthGuard demo.
Models are loaded from Seyomi/synthguard-kmer automatically.
"""

import os
os.environ["SYNTHGUARD_MODEL_DIR"] = "models/synthguard_kmer"

# Load models before building UI
from demo import load_models, build_demo
load_models("models/synthguard_kmer", "Seyomi/synthguard-kmer")

demo = build_demo()
demo.launch()
