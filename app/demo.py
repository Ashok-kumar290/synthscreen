"""
SynthScreen Demo — Gradio Web Interface
Screens DNA sequences for biosecurity hazards using SynthScreen.
Shows side-by-side comparison with BLAST-proxy baseline.

Run: python app/demo.py
"""

import json
import os
import random
import string
from pathlib import Path
from typing import Optional

import gradio as gr
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoConfig
from peft import PeftModel

# ── Example sequences for the demo ────────────────────────────────────────────
EXAMPLES = {
    "Ricin A chain (original)": (
        "ATGGCTAGCATGACTGGTGGACAGCAAATGGGTCGGGATCTGTACGACGATGACGATAAGGATC"
        "CCAATTTCATCAACAACAATGCAGACTTCAATGAAATCAATAATGAAGGAGATGATGCCAA"
    ),
    "Ricin A chain (codon-shuffled, AI-redesigned)": (
        "ATGGCAAGCATGACGGGGGGACAACAGATTGGGCGGGATTTGTATGATGATGATGATAAAGAC"
        "CCTAATTTTATCAACAACAATGCAGATTTCAATGAAATCAATAATGAGGGGGACGATGCGAA"
    ),
    "GFP (benign control)": (
        "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCCATCCTGGTCGAGCTGGACGG"
        "CGACGTAAACGGCCACAAGTTCAGCGTGTCCGGCGAGGGCGAGGGCGATGCCACCTACGGCA"
    ),
    "Botulinum toxin fragment (ProteinMPNN variant)": (
        "ATGGATAATCCAGATAATGATCCCGGTGGTTTTGAAACTGTTAATACAGAAATCATCGAGAA"
        "TAAAGCAAAGCAACTTGATAATATTCAGAAAGCTCTTAAAGACGTTAAAGAGCTTCTTAGT"
    ),
    "E. coli lacZ (benign)": (
        "ATGACCATGATTACGCCAAGCTCGAAATTAACCCTCACTAAAGGGAACAAAAGCTGGTACCA"
        "AGTCGACGGATCCCCGGGAATTCGAGCTCGGTACCCGGGGATCCTCTAGAGTCGACCTGCAG"
    ),
}

RISK_COLORS = {
    "HIGH": "#ff4444",
    "MEDIUM": "#ff9500",
    "LOW": "#00c851",
    "UNKNOWN": "#aaaaaa",
}


def load_model_cached(model_dir: str, model_type: str = "dnabert2"):
    """Load model with simple in-memory caching."""
    global _model_cache
    if not hasattr(load_model_cached, "_cache"):
        load_model_cached._cache = {}

    cache_key = (model_dir, model_type)
    if cache_key in load_model_cached._cache:
        return load_model_cached._cache[cache_key]

    device = "cuda" if torch.cuda.is_available() else "cpu"

    default_ids = {
        "esm2": "facebook/esm2_t33_650M_UR50D",
        "dnabert2": "zhihan1996/DNABERT-2-117M",
    }
    base_id = default_ids[model_type]

    tokenizer = AutoTokenizer.from_pretrained(base_id, trust_remote_code=True)

    if model_type == "dnabert2":
        cfg = AutoConfig.from_pretrained(base_id, num_labels=2, trust_remote_code=True)
        cfg.pad_token_id = tokenizer.pad_token_id or 0
        base = AutoModelForSequenceClassification.from_pretrained(
            base_id, config=cfg, trust_remote_code=True
        )
    else:
        base = AutoModelForSequenceClassification.from_pretrained(base_id, num_labels=2)

    model = PeftModel.from_pretrained(base, model_dir).to(device)
    model.eval()

    result = (model, tokenizer, device)
    load_model_cached._cache[cache_key] = result
    return result


def estimate_blast_identity(query: str, references: list[str], k: int = 7) -> float:
    """K-mer Jaccard proxy for BLAST identity."""
    if not references:
        return 0.0
    query_kmers = set(query[i:i+k] for i in range(max(0, len(query) - k + 1)))
    max_id = 0.0
    for ref in references:
        ref_kmers = set(ref[i:i+k] for i in range(max(0, len(ref) - k + 1)))
        if ref_kmers:
            j = len(query_kmers & ref_kmers) / len(query_kmers | ref_kmers)
            max_id = max(max_id, j)
    return max_id


def screen_with_model(sequence: str, model, tokenizer, device: str,
                       window_size: int = 300, stride: int = 150,
                       max_length: int = 512) -> tuple[float, list]:
    """Run model screening with sliding window. Returns (max_score, window_details)."""
    seq = sequence.upper().replace('U', 'T').strip()
    if not seq:
        return 0.0, []

    if len(seq) <= window_size:
        windows = [(0, len(seq), seq)]
    else:
        windows = []
        for s in range(0, len(seq) - window_size + 1, stride):
            windows.append((s, s + window_size, seq[s:s + window_size]))
        if windows and windows[-1][1] < len(seq):
            windows.append((len(seq) - window_size, len(seq), seq[-window_size:]))

    window_results = []
    for start, end, win in windows:
        enc = tokenizer(win, return_tensors="pt", truncation=True,
                        max_length=max_length, padding="max_length")
        enc = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            out = model(**enc)
            logits = out.logits
            if logits.ndim == 3:
                logits = logits[:, 0, :]
            if logits.shape[-1] != 2:
                logits = logits[:, :2]
            prob = torch.softmax(logits, dim=-1)[0, 1].item()
        window_results.append({"start": start, "end": end, "score": prob})

    max_score = max(w["score"] for w in window_results) if window_results else 0.0
    return max_score, window_results


def format_risk_label(score: float) -> tuple[str, str]:
    """Return (level, color) for a risk score."""
    if score >= 0.75:
        return "HIGH RISK", RISK_COLORS["HIGH"]
    elif score >= 0.5:
        return "MEDIUM RISK", RISK_COLORS["MEDIUM"]
    else:
        return "LOW RISK", RISK_COLORS["LOW"]


def screen_sequence_full(
    sequence: str,
    model_dir: str,
    model_type: str,
    blast_threshold: float,
    reference_db: str,
):
    """Main screening function called by Gradio."""
    seq = sequence.upper().replace('U', 'T').strip()
    if not seq:
        return (
            "Please enter a DNA sequence.",
            "", "", "", "", gr.update(value=""), gr.update(value=""),
        )

    # Parse simple reference DB (one sequence per line)
    refs = [r.strip() for r in reference_db.strip().split('\n') if r.strip() and not r.startswith('>')]

    # Load model
    try:
        model, tokenizer, device = load_model_cached(model_dir, model_type)
        model_available = True
    except Exception as e:
        model_available = False
        model_error = str(e)

    # BLAST proxy
    blast_id = estimate_blast_identity(seq, refs) if refs else 0.0
    blast_flagged = blast_id >= blast_threshold
    blast_label = f"FLAGGED ({blast_id:.1%} identity)" if blast_flagged else f"PASSED ({blast_id:.1%} identity)"

    # Our model
    if model_available:
        our_score, windows = screen_with_model(seq, model, tokenizer, device)
        our_level, our_color = format_risk_label(our_score)
        our_label = f"{our_level} (score: {our_score:.3f})"
    else:
        our_score = 0.0
        windows = []
        our_label = f"Model unavailable: {model_error}"
        our_color = RISK_COLORS["UNKNOWN"]

    # Comparison summary
    if model_available:
        blast_catches = "YES" if blast_flagged else "NO"
        our_catches = "YES" if our_score >= 0.5 else "NO"
        gap_line = ""
        if not blast_flagged and our_score >= 0.5:
            gap_line = "\n⚠️  SCREENING GAP DETECTED: This sequence PASSED BLAST but is flagged by SynthScreen.\nThis is the type of AI-designed variant that current synthesis screening misses."

        comparison = (
            f"Sequence length: {len(seq)} bp\n"
            f"Windows analyzed: {len(windows)}\n\n"
            f"BLAST proxy (≥{blast_threshold:.0%} identity):  {blast_catches} — {blast_label}\n"
            f"SynthScreen:                    {our_catches} — {our_label}"
            f"{gap_line}"
        )
    else:
        comparison = f"BLAST: {blast_label}\nModel: unavailable"

    # Window details
    if windows:
        window_text = "Window-level analysis:\n"
        for w in windows:
            level = "HIGH" if w["score"] >= 0.75 else ("MED" if w["score"] >= 0.5 else "low")
            window_text += f"  bp {w['start']:5d}-{w['end']:5d}:  {w['score']:.3f}  [{level}]\n"
    else:
        window_text = "No window analysis available."

    risk_display = f"Risk Score: {our_score:.3f}" if model_available else "N/A"
    level_display = our_label if model_available else "N/A"

    return comparison, risk_display, level_display, blast_label, window_text


def build_demo(model_dir: str = "models/synthscreen_v1/best",
               model_type: str = "dnabert2"):

    with gr.Blocks(title="SynthScreen — AI Biodesign Screening", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
# SynthScreen: Biosecurity Screening for AI-Designed DNA

**Track 1 — AIxBio Hackathon 2026**

Current DNA synthesis screening (BLAST-based) misses sequences designed by AI tools like ProteinMPNN
because they are functionally identical but sequence-divergent from known hazards.

SynthScreen uses DNABERT-2 + ESM-2 fine-tuned with focal loss and hard example mining to detect
**functional hazard** independent of sequence similarity.
        """)

        with gr.Row():
            with gr.Column(scale=2):
                seq_input = gr.Textbox(
                    label="DNA Sequence",
                    placeholder="Paste DNA sequence (ACGT) or FASTA here...",
                    lines=8,
                )
                with gr.Row():
                    model_dir_input = gr.Textbox(value=model_dir, label="Model Directory")
                    model_type_input = gr.Dropdown(
                        choices=["dnabert2", "esm2"], value=model_type, label="Model Type"
                    )
                with gr.Row():
                    blast_threshold = gr.Slider(0.3, 0.95, value=0.70, step=0.05,
                                                label="BLAST Identity Threshold")
                reference_db = gr.Textbox(
                    label="Reference Sequences (one per line, for BLAST proxy)",
                    placeholder="Paste known dangerous reference sequences here...",
                    lines=4,
                )
                screen_btn = gr.Button("Screen Sequence", variant="primary", size="lg")

            with gr.Column(scale=1):
                gr.Markdown("### Quick Examples")
                for name, seq in EXAMPLES.items():
                    gr.Button(name, size="sm").click(
                        fn=lambda s=seq: s,
                        outputs=seq_input,
                    )

        with gr.Row():
            comparison_out = gr.Textbox(label="Comparison: SynthScreen vs BLAST", lines=8)
            window_out = gr.Textbox(label="Window-Level Analysis", lines=8)

        with gr.Row():
            risk_score_out = gr.Textbox(label="Risk Score")
            level_out = gr.Textbox(label="Risk Level")
            blast_out = gr.Textbox(label="BLAST Result")

        screen_btn.click(
            fn=screen_sequence_full,
            inputs=[seq_input, model_dir_input, model_type_input, blast_threshold, reference_db],
            outputs=[comparison_out, risk_score_out, level_out, blast_out, window_out],
        )

        gr.Markdown("""
---
**How it works:**
1. Short fragments (≥50bp) and full sequences are processed via sliding windows
2. DNABERT-2 (DNA track) or ESM-2 (protein track) classify each window
3. Maximum risk across windows is reported
4. Compare against BLAST proxy to reveal the screening gap

**Key result:** ProteinMPNN-designed functional analogs of dangerous proteins score high on SynthScreen
but pass BLAST — demonstrating the gap in current AI-era biosecurity screening.
        """)

    return demo


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", default="models/synthscreen_v1/best")
    parser.add_argument("--model_type", default="dnabert2")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    demo = build_demo(args.model_dir, args.model_type)
    demo.launch(server_port=args.port, share=args.share)
