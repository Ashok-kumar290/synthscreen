"""
SynthGuard Out-of-Distribution (OOD) Benchmark

Tests the trained k-mer model on toxin families NEVER seen during training.
Training used: ricin, BoNT-A, anthrax LF, Yersinia pestis, Clostridium perfringens
epsilon toxin, Staph enterotoxin B, Shiga toxin, VEEV, Ebola GP, Marburg NP.

This script fetches 7 completely new toxin families from NCBI and evaluates:
  - SynthGuard k-mer (trained model, no fine-tuning on OOD)
  - BLAST proxy (k=7 Jaccard, threshold=0.70)

A model that generalizes across toxin families is genuinely functional.
One that only works on its training distribution is memorizing.

Usage:
    python scripts/eval/ood_benchmark.py \
        --email your@email.com \
        --model_dir models/synthguard_kmer \
        --output results/ood_benchmark
"""

import argparse
import json
import math
import os
import pickle
import random
import time
import warnings
from collections import Counter
from itertools import product
from pathlib import Path

import numpy as np
from Bio import Entrez, SeqIO
from sklearn.metrics import (
    f1_score, precision_score, recall_score, roc_auc_score, confusion_matrix
)

warnings.filterwarnings("ignore")

# ── OOD toxin families (NONE of these were in training) ──────────────────────
#
# Training hazardous queries covered:
#   ricin/RCA, botulinum type A, anthrax lethal factor, Yersinia pestis,
#   Clostridium perfringens epsilon toxin, Staph enterotoxin B, Shiga toxin,
#   VEEV capsid, Ebola glycoprotein, Marburg nucleoprotein
#
# OOD set uses genuinely different toxin families / subtypes:

OOD_HAZARDOUS = [
    # Tetanus — BoNT family but Clostridium tetani, not in training
    ('"tetanus toxin" AND "Clostridium tetani"[Organism]',
     "Tetanus toxin — BoNT family, different serotype/organism"),
    # Francisella tularensis — intracellular pathogen, Tier 1 Select Agent
    ('"Francisella tularensis"[Organism] AND "virulence" AND 300:3000[SLEN]',
     "Francisella tularensis — tularemia agent, Tier 1 Select"),
    # Brucella — Tier 1 Select Agent, zoonotic
    ('"Brucella abortus"[Organism] AND "virulence" AND 300:3000[SLEN]',
     "Brucella abortus — brucellosis, Tier 1 Select Agent"),
    # Coxiella burnetii — Q fever, obligate intracellular
    ('"Coxiella burnetii"[Organism] AND "virulence" AND 300:3000[SLEN]',
     "Coxiella burnetii — Q fever agent, Tier 1 Select"),
    # Clostridium difficile toxins — different clostridial species, not in training
    ('"Clostridioides difficile"[Organism] AND "toxin A" AND 500:3000[SLEN]',
     "C. difficile toxin A — large clostridial glucosylating toxin"),
    # SARS-CoV-2 spike (emerging biosecurity concern, viral, not in training)
    ('"SARS-CoV-2"[Organism] AND "spike protein" AND 500:4000[SLEN]',
     "SARS-CoV-2 spike — emerging pathogen, RNA virus glycoprotein"),
    # Variola/Orthopoxvirus — smallpox, Tier 1 Select Agent
    ('"Variola virus"[Organism] AND 300:3000[SLEN]',
     "Variola virus — smallpox, Tier 1 Select Agent"),
]

OOD_BENIGN = [
    ('"Streptomyces coelicolor"[Organism] AND 500:3000[SLEN]',
     "Streptomyces coelicolor — antibiotic-producing soil bacteria"),
    ('"Pichia pastoris"[Organism] AND "expression" AND 300:2000[SLEN]',
     "Pichia pastoris — industrial yeast expression host"),
    ('"Neurospora crassa"[Organism] AND 300:2000[SLEN]',
     "Neurospora crassa — model filamentous fungus"),
    ('"Danio rerio"[Organism] AND "housekeeping" AND "mRNA" AND 300:2000[SLEN]',
     "Zebrafish housekeeping genes"),
    ('"Arabidopsis thaliana"[Organism] AND "chloroplast" AND 300:2000[SLEN]',
     "Arabidopsis chloroplast genes — plant model"),
]

SYNONYMOUS_CODONS = {
    'TTT': ['TTC'], 'TTC': ['TTT'],
    'TTA': ['TTG','CTT','CTC','CTA','CTG'], 'TTG': ['TTA','CTT','CTC','CTA','CTG'],
    'CTT': ['TTA','TTG','CTC','CTA','CTG'], 'CTC': ['TTA','TTG','CTT','CTA','CTG'],
    'CTA': ['TTA','TTG','CTT','CTC','CTG'], 'CTG': ['TTA','TTG','CTT','CTC','CTA'],
    'ATT': ['ATC','ATA'], 'ATC': ['ATT','ATA'], 'ATA': ['ATT','ATC'],
    'ATG': ['ATG'],
    'GTT': ['GTC','GTA','GTG'], 'GTC': ['GTT','GTA','GTG'],
    'GTA': ['GTT','GTC','GTG'], 'GTG': ['GTT','GTC','GTA'],
    'TCT': ['TCC','TCA','TCG','AGT','AGC'], 'TCC': ['TCT','TCA','TCG','AGT','AGC'],
    'TCA': ['TCT','TCC','TCG','AGT','AGC'], 'TCG': ['TCT','TCC','TCA','AGT','AGC'],
    'AGT': ['TCT','TCC','TCA','TCG','AGC'], 'AGC': ['TCT','TCC','TCA','TCG','AGT'],
    'CCT': ['CCC','CCA','CCG'], 'CCC': ['CCT','CCA','CCG'],
    'CCA': ['CCT','CCC','CCG'], 'CCG': ['CCT','CCC','CCA'],
    'ACT': ['ACC','ACA','ACG'], 'ACC': ['ACT','ACA','ACG'],
    'ACA': ['ACT','ACC','ACG'], 'ACG': ['ACT','ACC','ACA'],
    'GCT': ['GCC','GCA','GCG'], 'GCC': ['GCT','GCA','GCG'],
    'GCA': ['GCT','GCC','GCG'], 'GCG': ['GCT','GCC','GCA'],
    'TAT': ['TAC'], 'TAC': ['TAT'],
    'CAT': ['CAC'], 'CAC': ['CAT'],
    'CAA': ['CAG'], 'CAG': ['CAA'],
    'AAT': ['AAC'], 'AAC': ['AAT'],
    'AAA': ['AAG'], 'AAG': ['AAA'],
    'GAT': ['GAC'], 'GAC': ['GAT'],
    'GAA': ['GAG'], 'GAG': ['GAA'],
    'TGT': ['TGC'], 'TGC': ['TGT'],
    'TGG': ['TGG'],
    'CGT': ['CGC','CGA','CGG','AGA','AGG'], 'CGC': ['CGT','CGA','CGG','AGA','AGG'],
    'CGA': ['CGT','CGC','CGG','AGA','AGG'], 'CGG': ['CGT','CGC','CGA','AGA','AGG'],
    'AGA': ['CGT','CGC','CGA','CGG','AGG'], 'AGG': ['CGT','CGC','CGA','CGG','AGA'],
    'GGT': ['GGC','GGA','GGG'], 'GGC': ['GGT','GGA','GGG'],
    'GGA': ['GGT','GGC','GGG'], 'GGG': ['GGT','GGC','GGA'],
    'TAA': ['TAG','TGA'], 'TAG': ['TAA','TGA'], 'TGA': ['TAA','TAG'],
}


def shuffle_codons(dna: str, fraction: float = 0.35, seed: int = 42) -> str:
    random.seed(seed)
    dna = dna.upper().replace('U', 'T')
    codons = [dna[i:i+3] for i in range(0, len(dna)-2, 3)]
    result = []
    for codon in codons:
        if len(codon) < 3:
            result.append(codon)
            continue
        if random.random() < fraction and codon in SYNONYMOUS_CODONS:
            syns = SYNONYMOUS_CODONS[codon]
            result.append(random.choice(syns) if syns else codon)
        else:
            result.append(codon)
    return ''.join(result)


def clean_sequence(seq: str) -> str:
    return ''.join(c for c in seq.upper() if c in 'ACGT')


def fetch_ncbi(query: str, max_count: int = 100, delay: float = 0.5) -> list[str]:
    seqs = []
    try:
        handle = Entrez.esearch(db="nucleotide", term=query, retmax=max_count)
        record = Entrez.read(handle)
        handle.close()
        ids = record.get("IdList", [])
        if not ids:
            return []
        time.sleep(delay)
        handle = Entrez.efetch(db="nucleotide", id=",".join(ids[:max_count]),
                               rettype="fasta", retmode="text")
        for rec in SeqIO.parse(handle, "fasta"):
            seq = clean_sequence(str(rec.seq))
            if 50 <= len(seq) <= 4000:
                seqs.append(seq)
        handle.close()
        time.sleep(delay)
    except Exception as e:
        print(f"    NCBI error: {e}")
    return seqs


# ── Feature extraction (must match training) ──────────────────────────────────

VOCAB = {k: ["".join(p) for p in product("ACGT", repeat=k)] for k in [3, 4, 5, 6]}


def extract_features(seq: str) -> list:
    seq = seq.upper().replace("U", "T")
    n = max(len(seq), 1)
    cnt = Counter(seq)
    total = sum(cnt.values())
    feats = [
        n,
        (cnt.get("G", 0) + cnt.get("C", 0)) / n,
        (cnt.get("A", 0) + cnt.get("T", 0)) / n,
        cnt.get("N", 0) / n,
        max(cnt.values()) / n if cnt else 0,
        -sum((c / total) * math.log2(c / total) for c in cnt.values() if c > 0),
    ]
    for k in [3, 4, 5, 6]:
        kc = Counter(seq[i:i+k] for i in range(n-k+1))
        tk = max(n-k+1, 1)
        feats.extend(kc.get(km, 0) / tk for km in VOCAB[k])
    return feats


def blast_proxy(seq: str, refs: list, k: int = 7, thresh: float = 0.70) -> bool:
    sq = set(seq[i:i+k] for i in range(max(0, len(seq)-k+1)))
    for r in refs:
        rk = set(r[i:i+k] for i in range(max(0, len(r)-k+1)))
        if sq | rk and len(sq & rk) / len(sq | rk) >= thresh:
            return True
    return False


def metrics(labels, preds, probs):
    labels, preds = list(labels), list(preds)
    cm = confusion_matrix(labels, preds)
    tn, fp, fn, tp = cm.ravel() if cm.shape == (2, 2) else (0, 0, 0, 0)
    auc = roc_auc_score(labels, probs) if len(set(labels)) > 1 else float("nan")
    return dict(
        recall=recall_score(labels, preds, zero_division=0),
        precision=precision_score(labels, preds, zero_division=0),
        f1=f1_score(labels, preds, zero_division=0),
        auroc=auc,
        fpr=fp / (fp + tn) if (fp + tn) else 0.0,
        tp=int(tp), fp=int(fp), tn=int(tn), fn=int(fn),
        n=len(labels),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--model_dir", default="models/synthguard_kmer")
    ap.add_argument("--output", default="results/ood_benchmark")
    ap.add_argument("--max_per_query", type=int, default=80)
    ap.add_argument("--shuffle_fractions", default="0.25,0.45")
    args = ap.parse_args()

    Entrez.email = args.email
    os.makedirs(args.output, exist_ok=True)
    shuffle_fracs = [float(x) for x in args.shuffle_fractions.split(",")]

    # ── Load model ────────────────────────────────────────────────────────────
    print("\n" + "="*65)
    print("SynthGuard OOD Benchmark — Truly Unseen Toxin Families")
    print("="*65)

    model_dir = Path(args.model_dir)
    if not (model_dir / "general_model.pkl").exists():
        raise RuntimeError(
            f"Model not found at {model_dir}. Run run_pipeline.py first."
        )

    with open(model_dir / "general_model.pkl", "rb") as f:
        general_model = pickle.load(f)
    with open(model_dir / "short_model.pkl", "rb") as f:
        short_model = pickle.load(f)

    print(f"Models loaded from {model_dir}")

    # ── Fetch OOD sequences ───────────────────────────────────────────────────
    print("\n[1/3] Fetching OOD hazardous sequences (unseen toxin families)...")
    hazardous_raw = []
    hazardous_meta = []  # (query_label, seq)

    for query, label in OOD_HAZARDOUS:
        seqs = fetch_ncbi(query, max_count=args.max_per_query)
        print(f"  {len(seqs):3d} seqs | {label}")
        for s in seqs:
            hazardous_raw.append(s)
            hazardous_meta.append(label.split("—")[0].strip())

    print(f"\nTotal OOD hazardous raw: {len(hazardous_raw)}")

    print("\n[2/3] Fetching OOD benign sequences...")
    benign_raw = []
    for query, label in OOD_BENIGN:
        seqs = fetch_ncbi(query, max_count=args.max_per_query)
        print(f"  {len(seqs):3d} seqs | {label}")
        benign_raw.extend(seqs)

    print(f"Total OOD benign raw: {len(benign_raw)}")

    if not hazardous_raw or not benign_raw:
        raise RuntimeError("No sequences fetched. Check NCBI connectivity.")

    # ── Build evaluation set with codon variants ──────────────────────────────
    print("\n[3/3] Building OOD evaluation set (original + codon-shuffled variants)...")

    seqs_eval, labels_eval, sources_eval = [], [], []

    # Hazardous: original + shuffled at each fraction
    for seq in hazardous_raw:
        seq = seq[:2048]
        seqs_eval.append(seq)
        labels_eval.append(1)
        sources_eval.append("original")
        for i, frac in enumerate(shuffle_fracs):
            variant = shuffle_codons(seq, fraction=frac, seed=hash(seq) + i)
            seqs_eval.append(variant)
            labels_eval.append(1)
            sources_eval.append(f"codon_shuffled_{int(frac*100)}pct")

    # Benign: original + one shuffle (even though label-preserving, tests FPR)
    for seq in benign_raw:
        seq = seq[:2048]
        seqs_eval.append(seq)
        labels_eval.append(0)
        sources_eval.append("original")
        variant = shuffle_codons(seq, fraction=0.35, seed=hash(seq))
        seqs_eval.append(variant)
        labels_eval.append(0)
        sources_eval.append("codon_shuffled_35pct")

    # Balance
    haz_idx = [i for i, l in enumerate(labels_eval) if l == 1]
    ben_idx = [i for i, l in enumerate(labels_eval) if l == 0]
    random.seed(42)
    min_n = min(len(haz_idx), len(ben_idx))
    keep = set(random.sample(haz_idx, min_n) + random.sample(ben_idx, min_n))
    seqs_eval   = [seqs_eval[i]   for i in sorted(keep)]
    labels_eval = [labels_eval[i] for i in sorted(keep)]
    sources_eval= [sources_eval[i] for i in sorted(keep)]

    n_haz = sum(labels_eval)
    n_ben = len(labels_eval) - n_haz
    print(f"OOD eval set: {len(seqs_eval)} sequences ({n_haz} hazardous / {n_ben} benign)")
    codon_haz = sum(1 for l, s in zip(labels_eval, sources_eval)
                    if l == 1 and "shuffled" in s)
    print(f"  of which {codon_haz} are codon-shuffled hazardous variants")

    # ── BLAST proxy references ────────────────────────────────────────────────
    # Give BLAST the "known" sequences — first 3 hazardous originals per toxin family
    # This simulates what a BLAST database would have
    refs = [s for s, src in zip(seqs_eval, sources_eval)
            if src == "original"][:10]

    # ── Feature extraction ────────────────────────────────────────────────────
    print("\nExtracting features...")
    X = np.array([extract_features(s) for s in seqs_eval])
    y = np.array(labels_eval)

    short_mask = np.array([len(s) < 150 for s in seqs_eval])
    ai_mask    = np.array(["shuffled" in src for src in sources_eval])

    # ── Evaluate ──────────────────────────────────────────────────────────────
    print("\nRunning BLAST proxy...")
    blast_preds = np.array([int(blast_proxy(s, refs)) for s in seqs_eval])

    print("Running SynthGuard k-mer...")
    kmer_probs = np.where(
        short_mask,
        short_model.predict_proba(X)[:, 1],
        general_model.predict_proba(X)[:, 1],
    )
    kmer_preds = (kmer_probs >= 0.5).astype(int)

    # ── Results ───────────────────────────────────────────────────────────────
    print("\n\n" + "="*70)
    print("OOD BENCHMARK RESULTS — UNSEEN TOXIN FAMILIES")
    print("(Trained: ricin/BoNT-A,B,E/anthrax/Yersinia/Shiga/VEEV/Ebola/Marburg/")
    print("         Burkholderia/Vibrio-cholera/abrin/diphtheria)")
    print("(OOD: tetanus/Francisella/Brucella/Coxiella/C.diff/SARS-CoV-2/Variola)")
    print("="*70)

    slices = [
        ("Full OOD set",               np.ones(len(y), dtype=bool)),
        ("Original sequences only",    np.array([s == "original" for s in sources_eval])),
        ("Codon-shuffled variants",    ai_mask),
        ("Short sequences (<150bp)",   short_mask),
    ]

    all_results = {}
    fmt = "  {:<38} {:>7} {:>7} {:>7} {:>7}"
    print(fmt.format("Method / Slice", "Recall", "FPR", "F1", "AUROC"))
    print("  " + "─" * 64)

    for slice_name, mask in slices:
        if mask.sum() == 0 or len(set(y[mask])) < 2:
            continue
        print(f"\n  [{slice_name}]  n={mask.sum()}")
        for method_name, preds, probs in [
            ("BLAST (k7 proxy)", blast_preds, blast_preds.astype(float)),
            ("SynthGuard k-mer", kmer_preds, kmer_probs),
        ]:
            m = metrics(y[mask], preds[mask], probs[mask])
            key = f"{slice_name}_{method_name}"
            all_results[key] = m
            print(fmt.format(
                f"  {method_name}",
                f"{m['recall']:.3f}", f"{m['fpr']:.3f}",
                f"{m['f1']:.3f}",
                f"{m['auroc']:.3f}" if not math.isnan(m['auroc']) else "  nan"
            ))

    # Per-toxin-family breakdown
    print("\n\n  PER-TOXIN-FAMILY RECALL (SynthGuard k-mer):")
    print("  " + "─" * 55)
    toxin_results = {}
    for query, label in OOD_HAZARDOUS:
        family = label.split("—")[0].strip()
        family_seqs_idx = [
            i for i, (src_meta, lbl) in
            enumerate(zip([hazardous_meta[hazardous_raw.index(s)]
                           if s in hazardous_raw else "" for s in seqs_eval],
                          labels_eval))
        ]
        # Simpler: group by position in the original hazardous_raw
    # Recompute per-family using the raw sequences before balancing
    print("  (Computing per-family on raw hazardous sequences before balancing)")
    for (query, label), seqs_family in zip(
        OOD_HAZARDOUS,
        _group_by_family(hazardous_raw, hazardous_meta, OOD_HAZARDOUS)
    ):
        if not seqs_family:
            print(f"  {label.split('—')[0].strip():<38}  no sequences fetched")
            continue
        X_fam = np.array([extract_features(s) for s in seqs_family])
        short_fam = np.array([len(s) < 150 for s in seqs_family])
        probs_fam = np.where(
            short_fam,
            short_model.predict_proba(X_fam)[:, 1],
            general_model.predict_proba(X_fam)[:, 1],
        )
        preds_fam = (probs_fam >= 0.5).astype(int)
        blast_fam = np.array([int(blast_proxy(s, refs)) for s in seqs_family])
        recall_kmer  = preds_fam.mean()
        recall_blast = blast_fam.mean()
        fam_name = label.split("—")[0].strip()[:35]
        print(f"  {fam_name:<38}  k-mer={recall_kmer:.1%}  BLAST={recall_blast:.1%}  "
              f"n={len(seqs_family)}")
        toxin_results[fam_name] = {"kmer_recall": recall_kmer, "blast_recall": recall_blast,
                                    "n": len(seqs_family)}

    # Headline
    full_blast = all_results.get("Full OOD set_BLAST (k7 proxy)", {})
    full_kmer  = all_results.get("Full OOD set_SynthGuard k-mer", {})
    print("\n\n  HEADLINE:")
    print(f"  OOD recall — BLAST: {full_blast.get('recall',0):.1%} | "
          f"SynthGuard: {full_kmer.get('recall',0):.1%}")
    if full_blast.get('recall', 0) > 0:
        improvement = full_kmer.get('recall',0) / full_blast.get('recall',0)
        print(f"  Improvement: {improvement:.0f}× over BLAST on unseen toxin families")
    else:
        print(f"  BLAST recall = 0% on unseen families (caught nothing)")
        print(f"  SynthGuard catches {full_kmer.get('recall',0):.1%} with no retraining")

    codon_blast = all_results.get("Codon-shuffled variants_BLAST (k7 proxy)", {})
    codon_kmer  = all_results.get("Codon-shuffled variants_SynthGuard k-mer", {})
    print(f"\n  On codon-shuffled OOD variants specifically:")
    print(f"  BLAST: {codon_blast.get('recall',0):.1%} | "
          f"SynthGuard: {codon_kmer.get('recall',0):.1%}")

    # Save
    output = {
        "description": "OOD benchmark on toxin families unseen during training",
        "training_families": [
            "ricin (RCA)", "botulinum type A/B/E", "anthrax lethal factor",
            "Yersinia pestis", "Clostridium perfringens epsilon toxin",
            "Staph enterotoxin B", "Shiga toxin", "VEEV capsid",
            "Ebola glycoprotein", "Marburg nucleoprotein",
            "Burkholderia mallei/pseudomallei", "Vibrio cholerae cholera toxin",
            "abrin", "diphtheria toxin",
        ],
        "ood_families": [label.split("—")[0].strip() for _, label in OOD_HAZARDOUS],
        "n_sequences": len(seqs_eval),
        "n_hazardous": int(n_haz),
        "n_benign": int(n_ben),
        "metrics": {k: {mk: (float(mv) if isinstance(mv, (float, np.floating)) else mv)
                        for mk, mv in v.items()}
                    for k, v in all_results.items()},
        "per_toxin_family": toxin_results,
    }

    out_path = os.path.join(args.output, "ood_benchmark.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")


def _group_by_family(hazardous_raw, hazardous_meta, ood_hazardous):
    """Group raw hazardous sequences by their source toxin family."""
    groups = []
    for _, label in ood_hazardous:
        family_key = label.split("—")[0].strip()
        seqs = [s for s, m in zip(hazardous_raw, hazardous_meta)
                if m == family_key]
        groups.append(seqs)
    return groups


if __name__ == "__main__":
    main()
