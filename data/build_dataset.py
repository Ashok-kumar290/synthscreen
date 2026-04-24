"""
SynthScreen Dataset Builder
Fetches hazardous and benign DNA sequences from NCBI, applies codon-shuffling
augmentation to simulate AI-redesigned sequences, generates short fragments
(50-300bp) to stress-test screening against fragmented synthesis orders.

Usage:
    python data/build_dataset.py --email your@email.com --output data/processed/synthscreen_dna_v1_dataset
    python data/build_dataset.py --email your@email.com --api_key NCBI_KEY --max_per_query 500
"""

import argparse
import random
import time
import os
import json
from pathlib import Path
from typing import Optional

import numpy as np
from Bio import Entrez, SeqIO
from Bio.Seq import Seq
from datasets import Dataset, DatasetDict
from tqdm import tqdm


# ── Select agent / biosecurity-relevant gene queries ──────────────────────────
HAZARDOUS_QUERIES = [
    # Original 10 families
    '"ricin" AND "RCA" AND "Ricinus communis"[Organism]',
    '"botulinum toxin" AND "type A"[All Fields] AND 1000:5000[SLEN]',
    '"anthrax" AND "lethal factor" AND "Bacillus anthracis"[Organism]',
    '"Yersinia pestis"[Organism] AND "virulence factor" AND 500:4000[SLEN]',
    '"Clostridium perfringens"[Organism] AND "epsilon toxin"',
    '"Staphylococcal enterotoxin" AND "type B"',
    '"Shiga toxin" AND "Shiga-like"',
    '"Venezuelan equine encephalitis" AND "capsid"',
    '"Ebola virus" AND "glycoprotein" AND 500:3000[SLEN]',
    '"Marburg marburgvirus"[Organism] AND "nucleoprotein"',
    # Added: families that failed OOD — high-GC and marine pathogens
    '"Burkholderia mallei"[Organism] AND "virulence" AND 300:3000[SLEN]',
    '"Burkholderia pseudomallei"[Organism] AND "toxin" AND 300:3000[SLEN]',
    '"cholera toxin" AND "ctxA" AND "Vibrio cholerae"[Organism]',
    '"abrin" AND "Abrus precatorius"[Organism]',
    '"diphtheria toxin" AND "Corynebacterium diphtheriae"[Organism] AND 500:3000[SLEN]',
    # Added: broader Select Agent coverage
    '"botulinum toxin" AND "type B"[All Fields] AND 1000:5000[SLEN]',
    '"botulinum toxin" AND "type E"[All Fields] AND 1000:5000[SLEN]',
    '"Clostridium botulinum"[Organism] AND "neurotoxin" AND 500:4000[SLEN]',
    # Added: fix Brucella 30% recall — add to training
    '"Brucella abortus"[Organism] AND "virulence" AND 300:3000[SLEN]',
    '"Brucella melitensis"[Organism] AND "virulence" AND 300:3000[SLEN]',
    # Added: fix Coxiella 3.2% recall — AT-rich obligate intracellular pathogen
    '"Coxiella burnetii"[Organism] AND "virulence" AND 300:3000[SLEN]',
    '"Coxiella burnetii"[Organism] AND "effector" AND 300:3000[SLEN]',
    # Added: expand ricin coverage — RCA60 and RCA120 isoforms, codon variants
    '"Ricinus communis"[Organism] AND "ricin" AND "chain A" AND 500:3000[SLEN]',
    '"Ricinus communis"[Organism] AND "agglutinin" AND "RCA" AND 500:3000[SLEN]',
    # Added: abrin (structurally similar to ricin, closes coverage gap)
    '"Abrus precatorius"[Organism] AND "abrin" AND "chain A" AND 300:3000[SLEN]',
    # Added: Francisella tularensis (tularemia, Select Agent)
    '"Francisella tularensis"[Organism] AND "virulence" AND 300:3000[SLEN]',
    # Added: smallpox-adjacent poxvirus virulence factors
    '"Monkeypox virus"[Organism] AND "virulence" AND 300:3000[SLEN]',
]

# Publicly safe, benign sequences
BENIGN_QUERIES = [
    # Standard lab organisms
    '"Escherichia coli K-12"[Organism] AND "lacZ"',
    '"pUC19" AND "cloning vector"',
    '"enhanced green fluorescent protein" AND "EGFP"',
    '"Saccharomyces cerevisiae"[Organism] AND "housekeeping" AND 200:3000[SLEN]',
    '"Bacillus subtilis"[Organism] AND "sporulation" AND 500:3000[SLEN]',
    '"Homo sapiens"[Organism] AND "GAPDH" AND "mRNA"',
    '"Arabidopsis thaliana"[Organism] AND "actin" AND 300:2000[SLEN]',
    '"Mus musculus"[Organism] AND "beta actin" AND "mRNA"',
    '"synthetic construct"[Organism] AND "expression vector" AND 1000:5000[SLEN]',
    '"Lactobacillus acidophilus"[Organism] AND "16S ribosomal RNA"',
    # Added: diverse codon usage organisms — fix OOD FPR 52.7%
    # These have unusual GC/codon bias that the model incorrectly flagged as hazardous
    '"Streptomyces coelicolor"[Organism] AND 500:3000[SLEN]',
    '"Pichia pastoris"[Organism] AND "expression" AND 300:2000[SLEN]',
    '"Neurospora crassa"[Organism] AND 300:2000[SLEN]',
    '"Danio rerio"[Organism] AND "housekeeping" AND "mRNA" AND 300:2000[SLEN]',
    '"Aspergillus niger"[Organism] AND "enzyme" AND 300:3000[SLEN]',
    '"Trichoderma reesei"[Organism] AND "cellulase" AND 300:3000[SLEN]',
    '"Chlamydomonas reinhardtii"[Organism] AND 300:2000[SLEN]',
    # Added: fix high-GC false positives (Streptomyces 0.557 REVIEW)
    '"Mycobacterium smegmatis"[Organism] AND "housekeeping" AND 300:3000[SLEN]',
    '"Rhodococcus jostii"[Organism] AND 300:2000[SLEN]',
    '"Deinococcus radiodurans"[Organism] AND "housekeeping" AND 300:2000[SLEN]',
    '"Streptomyces venezuelae"[Organism] AND 300:2000[SLEN]',
]

# Standard genetic code: codon -> list of synonymous codons
SYNONYMOUS_CODONS = {
    'TTT': ['TTC'], 'TTC': ['TTT'],
    'TTA': ['TTG', 'CTT', 'CTC', 'CTA', 'CTG'],
    'TTG': ['TTA', 'CTT', 'CTC', 'CTA', 'CTG'],
    'CTT': ['TTA', 'TTG', 'CTC', 'CTA', 'CTG'],
    'CTC': ['TTA', 'TTG', 'CTT', 'CTA', 'CTG'],
    'CTA': ['TTA', 'TTG', 'CTT', 'CTC', 'CTG'],
    'CTG': ['TTA', 'TTG', 'CTT', 'CTC', 'CTA'],
    'ATT': ['ATC', 'ATA'], 'ATC': ['ATT', 'ATA'], 'ATA': ['ATT', 'ATC'],
    'ATG': ['ATG'],  # Met - only one codon
    'GTT': ['GTC', 'GTA', 'GTG'],
    'GTC': ['GTT', 'GTA', 'GTG'],
    'GTA': ['GTT', 'GTC', 'GTG'],
    'GTG': ['GTT', 'GTC', 'GTA'],
    'TCT': ['TCC', 'TCA', 'TCG', 'AGT', 'AGC'],
    'TCC': ['TCT', 'TCA', 'TCG', 'AGT', 'AGC'],
    'TCA': ['TCT', 'TCC', 'TCG', 'AGT', 'AGC'],
    'TCG': ['TCT', 'TCC', 'TCA', 'AGT', 'AGC'],
    'AGT': ['TCT', 'TCC', 'TCA', 'TCG', 'AGC'],
    'AGC': ['TCT', 'TCC', 'TCA', 'TCG', 'AGT'],
    'CCT': ['CCC', 'CCA', 'CCG'],
    'CCC': ['CCT', 'CCA', 'CCG'],
    'CCA': ['CCT', 'CCC', 'CCG'],
    'CCG': ['CCT', 'CCC', 'CCA'],
    'ACT': ['ACC', 'ACA', 'ACG'],
    'ACC': ['ACT', 'ACA', 'ACG'],
    'ACA': ['ACT', 'ACC', 'ACG'],
    'ACG': ['ACT', 'ACC', 'ACA'],
    'GCT': ['GCC', 'GCA', 'GCG'],
    'GCC': ['GCT', 'GCA', 'GCG'],
    'GCA': ['GCT', 'GCC', 'GCG'],
    'GCG': ['GCT', 'GCC', 'GCA'],
    'TAT': ['TAC'], 'TAC': ['TAT'],
    'TAA': ['TAG', 'TGA'], 'TAG': ['TAA', 'TGA'], 'TGA': ['TAA', 'TAG'],
    'CAT': ['CAC'], 'CAC': ['CAT'],
    'CAA': ['CAG'], 'CAG': ['CAA'],
    'AAT': ['AAC'], 'AAC': ['AAT'],
    'AAA': ['AAG'], 'AAG': ['AAA'],
    'GAT': ['GAC'], 'GAC': ['GAT'],
    'GAA': ['GAG'], 'GAG': ['GAA'],
    'TGT': ['TGC'], 'TGC': ['TGT'],
    'TGG': ['TGG'],  # Trp - only one codon
    'CGT': ['CGC', 'CGA', 'CGG', 'AGA', 'AGG'],
    'CGC': ['CGT', 'CGA', 'CGG', 'AGA', 'AGG'],
    'CGA': ['CGT', 'CGC', 'CGG', 'AGA', 'AGG'],
    'CGG': ['CGT', 'CGC', 'CGA', 'AGA', 'AGG'],
    'AGA': ['CGT', 'CGC', 'CGA', 'CGG', 'AGG'],
    'AGG': ['CGT', 'CGC', 'CGA', 'CGG', 'AGA'],
    'GGT': ['GGC', 'GGA', 'GGG'],
    'GGC': ['GGT', 'GGA', 'GGG'],
    'GGA': ['GGT', 'GGC', 'GGG'],
    'GGG': ['GGT', 'GGC', 'GGA'],
}


def shuffle_codons(dna: str, fraction: float = 0.35, seed: Optional[int] = None) -> str:
    """
    Replace `fraction` of codons with synonymous alternatives.
    Simulates codon-optimized / AI-redesigned sequences that evade BLAST.
    Only operates on in-frame codons from position 0.
    """
    if seed is not None:
        random.seed(seed)
    dna = dna.upper().replace('U', 'T')
    codons = [dna[i:i+3] for i in range(0, len(dna) - 2, 3)]
    result = []
    for codon in codons:
        if len(codon) < 3:
            result.append(codon)
            continue
        if random.random() < fraction and codon in SYNONYMOUS_CODONS:
            synonyms = SYNONYMOUS_CODONS[codon]
            result.append(random.choice(synonyms) if synonyms else codon)
        else:
            result.append(codon)
    return ''.join(result)


def reverse_complement(dna: str) -> str:
    return str(Seq(dna).reverse_complement())


def make_fragments(dna: str, min_len: int = 50, max_len: int = 300,
                   n_fragments: int = 3) -> list[str]:
    """Generate short fragments from a longer sequence (simulating fragmented orders)."""
    fragments = []
    if len(dna) < min_len:
        return [dna]
    for _ in range(n_fragments):
        frag_len = random.randint(min_len, min(max_len, len(dna)))
        start = random.randint(0, len(dna) - frag_len)
        fragments.append(dna[start:start + frag_len])
    return fragments


def clean_sequence(seq: str) -> str:
    """Keep only ACGT, uppercase."""
    return ''.join(c for c in seq.upper() if c in 'ACGT')


def fetch_sequences_ncbi(query: str, db: str = "nucleotide",
                          max_count: int = 200, delay: float = 0.4) -> list[str]:
    """Fetch sequences from NCBI with rate limiting."""
    sequences = []
    try:
        handle = Entrez.esearch(db=db, term=query, retmax=max_count)
        record = Entrez.read(handle)
        handle.close()
        ids = record.get("IdList", [])
        if not ids:
            return []

        time.sleep(delay)
        handle = Entrez.efetch(db=db, id=",".join(ids[:max_count]),
                               rettype="fasta", retmode="text")
        for rec in SeqIO.parse(handle, "fasta"):
            seq = clean_sequence(str(rec.seq))
            if len(seq) >= 50:
                sequences.append(seq)
        handle.close()
        time.sleep(delay)
    except Exception as e:
        print(f"  NCBI fetch error ({query[:60]}): {e}")
    return sequences


def build_examples(sequences: list[str], label: int,
                   include_variants: bool = True,
                   include_fragments: bool = True,
                   max_seq_len: int = 1024) -> list[dict]:
    """
    Convert raw sequences into training examples.
    - Full sequences (truncated to max_seq_len)
    - Codon-shuffled variants (label preserved — same function, evasive sequence)
    - Short fragments (label preserved — catch fragmented orders)
    """
    examples = []
    for seq in sequences:
        seq = seq[:max_seq_len]
        examples.append({"sequence": seq, "label": label, "source": "original"})

        if include_variants and label == 1:
            # Two variants per hazardous sequence at different shuffle rates
            for frac, seed_offset in [(0.25, 1), (0.45, 2)]:
                variant = shuffle_codons(seq, fraction=frac, seed=hash(seq) + seed_offset)
                examples.append({"sequence": variant, "label": label, "source": "codon_shuffled"})

        if include_fragments:
            n_frags = 4 if label == 1 else 2
            for frag in make_fragments(seq, n_fragments=n_frags):
                examples.append({"sequence": frag, "label": label, "source": "fragment"})

    return examples


def build_dataset(email: str, output_path: str, api_key: Optional[str] = None,
                  max_per_query: int = 200, seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)

    Entrez.email = email
    if api_key:
        Entrez.api_key = api_key

    print("=" * 60)
    print("SynthScreen Dataset Builder")
    print("=" * 60)

    # ── Fetch sequences ────────────────────────────────────────────
    hazardous_raw, benign_raw = [], []

    print("\n[1/4] Fetching hazardous sequences from NCBI...")
    for query in tqdm(HAZARDOUS_QUERIES):
        seqs = fetch_sequences_ncbi(query, max_count=max_per_query)
        hazardous_raw.extend(seqs)
        print(f"  {len(seqs):3d} sequences <- {query[:60]}")

    print(f"\nTotal hazardous: {len(hazardous_raw)}")

    print("\n[2/4] Fetching benign sequences from NCBI...")
    for query in tqdm(BENIGN_QUERIES):
        seqs = fetch_sequences_ncbi(query, max_count=max_per_query)
        benign_raw.extend(seqs)
        print(f"  {len(seqs):3d} sequences <- {query[:60]}")

    print(f"Total benign: {len(benign_raw)}")

    if not hazardous_raw or not benign_raw:
        raise RuntimeError("No sequences fetched. Check NCBI connectivity and queries.")

    # Deduplicate
    hazardous_raw = list(set(hazardous_raw))
    benign_raw = list(set(benign_raw))

    # ── Build examples ─────────────────────────────────────────────
    print("\n[3/4] Building training examples (original + codon variants + fragments)...")
    hazardous_examples = build_examples(hazardous_raw, label=1,
                                        include_variants=True, include_fragments=True)
    benign_examples = build_examples(benign_raw, label=0,
                                     include_variants=False, include_fragments=True)

    print(f"Hazardous examples: {len(hazardous_examples)}")
    print(f"Benign examples:    {len(benign_examples)}")

    # Balance classes
    min_count = min(len(hazardous_examples), len(benign_examples))
    random.shuffle(hazardous_examples)
    random.shuffle(benign_examples)
    all_examples = hazardous_examples[:min_count] + benign_examples[:min_count]
    random.shuffle(all_examples)

    print(f"Balanced total:     {len(all_examples)} ({min_count} each class)")

    # ── Split ──────────────────────────────────────────────────────
    print("\n[4/4] Creating train / validation / test splits (70/15/15)...")
    n = len(all_examples)
    n_train = int(0.70 * n)
    n_val = int(0.15 * n)

    splits = {
        "train": all_examples[:n_train],
        "validation": all_examples[n_train:n_train + n_val],
        "test": all_examples[n_train + n_val:],
    }

    for split_name, items in splits.items():
        haz = sum(1 for x in items if x["label"] == 1)
        print(f"  {split_name:12s}: {len(items):5d} total, {haz} hazardous, "
              f"{len(items)-haz} benign")

    dataset = DatasetDict({
        split: Dataset.from_list(items) for split, items in splits.items()
    })

    Path(output_path).mkdir(parents=True, exist_ok=True)
    dataset.save_to_disk(output_path)

    stats = {
        "total_examples": len(all_examples),
        "hazardous_raw": len(hazardous_raw),
        "benign_raw": len(benign_raw),
        "splits": {k: len(v) for k, v in splits.items()},
    }
    with open(os.path.join(output_path, "dataset_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\nDataset saved to: {output_path}")
    return dataset


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True, help="Your email for NCBI Entrez")
    parser.add_argument("--api_key", default=None, help="NCBI API key (optional, raises rate limit)")
    parser.add_argument("--output", default="data/processed/synthscreen_dna_v1_dataset")
    parser.add_argument("--max_per_query", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    build_dataset(
        email=args.email,
        output_path=args.output,
        api_key=args.api_key,
        max_per_query=args.max_per_query,
        seed=args.seed,
    )
