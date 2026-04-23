"""
Generate novel protein sequences for known dangerous proteins using ProteinMPNN.
This is the core of the Track 1 novel contribution:
  Known dangerous structure (PDB) → ProteinMPNN → novel sequences → back-translate to DNA
  → sequences that BLAST misses but funcscreen catches

These sequences ARE the adversarial gap in current DNA synthesis screening.

Dangerous PDB structures used (all publicly available):
  - 1IFS: Ricin A chain (toxin)
  - 3BTA: Botulinum toxin type A (light chain)
  - 1J7N: Anthrax lethal factor
  - 1ABR: Abrin A chain (toxin)
  - 1BC7: Diphtheria toxin A fragment

Usage (Colab):
    !pip install git+https://github.com/dauparas/ProteinMPNN.git
    python data/generate_mpnn_variants.py --output data/mpnn_variants.json --n_seqs 50
"""

import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Optional

import numpy as np

# Dangerous protein structures: (PDB ID, chain, description)
DANGEROUS_STRUCTURES = [
    ("1IFS", "A", "Ricin_A_chain_toxin"),
    ("3BTA", "A", "Botulinum_toxin_A_light_chain"),
    ("1J7N", "A", "Anthrax_lethal_factor"),
    ("1ABR", "A", "Abrin_A_chain_toxin"),
    ("1BC7", "B", "Diphtheria_toxin_A_fragment"),
]

# Benign control structures (same fold families but safe function)
BENIGN_STRUCTURES = [
    ("2LZM", "A", "T4_lysozyme"),
    ("1UBQ", "A", "Ubiquitin"),
    ("1CRN", "A", "Crambin"),
    ("1VII", "A", "Villin_headpiece"),
    ("2CI2", "I", "Chymotrypsin_inhibitor"),
]

# Codon tables for back-translation (organism -> codon preferences)
HUMAN_CODON_TABLE = {
    'A': ['GCC', 'GCT', 'GCA', 'GCG'],
    'R': ['AGG', 'AGA', 'CGG', 'CGC', 'CGA', 'CGT'],
    'N': ['AAC', 'AAT'],
    'D': ['GAC', 'GAT'],
    'C': ['TGC', 'TGT'],
    'Q': ['CAG', 'CAA'],
    'E': ['GAG', 'GAA'],
    'G': ['GGC', 'GGG', 'GGA', 'GGT'],
    'H': ['CAC', 'CAT'],
    'I': ['ATC', 'ATT', 'ATA'],
    'L': ['CTG', 'CTC', 'TTG', 'CTT', 'CTA', 'TTA'],
    'K': ['AAG', 'AAA'],
    'M': ['ATG'],
    'F': ['TTC', 'TTT'],
    'P': ['CCC', 'CCT', 'CCA', 'CCG'],
    'S': ['AGC', 'TCC', 'TCT', 'AGT', 'TCA', 'TCG'],
    'T': ['ACC', 'ACA', 'ACT', 'ACG'],
    'W': ['TGG'],
    'Y': ['TAC', 'TAT'],
    'V': ['GTG', 'GTC', 'GTT', 'GTA'],
    '*': ['TGA', 'TAA', 'TAG'],
}

ECOLI_CODON_TABLE = {
    'A': ['GCG', 'GCC', 'GCA', 'GCT'],
    'R': ['CGT', 'CGC', 'CGG', 'CGA', 'AGA', 'AGG'],
    'N': ['AAC', 'AAT'],
    'D': ['GAT', 'GAC'],
    'C': ['TGC', 'TGT'],
    'Q': ['CAG', 'CAA'],
    'E': ['GAA', 'GAG'],
    'G': ['GGC', 'GGT', 'GGA', 'GGG'],
    'H': ['CAT', 'CAC'],
    'I': ['ATT', 'ATC', 'ATA'],
    'L': ['CTG', 'TTA', 'TTG', 'CTT', 'CTC', 'CTA'],
    'K': ['AAA', 'AAG'],
    'M': ['ATG'],
    'F': ['TTT', 'TTC'],
    'P': ['CCG', 'CCA', 'CCT', 'CCC'],
    'S': ['AGC', 'TCT', 'TCC', 'TCA', 'TCG', 'AGT'],
    'T': ['ACC', 'ACA', 'ACT', 'ACG'],
    'W': ['TGG'],
    'Y': ['TAT', 'TAC'],
    'V': ['GTT', 'GTC', 'GTG', 'GTA'],
    '*': ['TAA', 'TGA', 'TAG'],
}


def protein_to_dna(protein_seq: str, codon_table: dict, seed: Optional[int] = None) -> str:
    """Back-translate protein to DNA using a weighted codon table."""
    if seed is not None:
        random.seed(seed)
    dna = []
    for aa in protein_seq.upper():
        if aa not in codon_table:
            aa = '*'  # stop codon for unknown
        codons = codon_table[aa]
        dna.append(random.choice(codons))
    return ''.join(dna)


def download_pdb(pdb_id: str, pdb_dir: str = "data/pdb_structures") -> Optional[str]:
    """Download PDB file using urllib."""
    import urllib.request
    os.makedirs(pdb_dir, exist_ok=True)
    pdb_path = os.path.join(pdb_dir, f"{pdb_id.lower()}.pdb")
    if os.path.exists(pdb_path):
        return pdb_path
    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    try:
        urllib.request.urlretrieve(url, pdb_path)
        return pdb_path
    except Exception as e:
        print(f"  Failed to download {pdb_id}: {e}")
        return None


def run_proteinmpnn(pdb_path: str, chain: str, n_seqs: int = 50,
                    temperature: float = 0.1,
                    mpnn_script_dir: str = "ProteinMPNN") -> list[str]:
    """
    Run ProteinMPNN on a PDB file to generate novel sequences.
    Returns list of generated amino acid sequences.

    Requires: git clone https://github.com/dauparas/ProteinMPNN
    """
    output_dir = f"data/mpnn_outputs/{Path(pdb_path).stem}"
    os.makedirs(output_dir, exist_ok=True)

    jsonl_path = os.path.join(output_dir, "input.jsonl")
    with open(jsonl_path, "w") as f:
        json.dump({"pdb_path": pdb_path, "chain_id_dict": {Path(pdb_path).stem: chain}}, f)
        f.write("\n")

    cmd = [
        sys.executable,
        os.path.join(mpnn_script_dir, "protein_mpnn_run.py"),
        "--pdb_path", pdb_path,
        "--pdb_path_chains", chain,
        "--out_folder", output_dir,
        "--num_seq_per_target", str(n_seqs),
        "--sampling_temp", str(temperature),
        "--seed", "42",
        "--batch_size", "1",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ProteinMPNN error: {result.stderr[:200]}")
        return []

    # Parse FASTA output
    sequences = []
    fasta_dir = os.path.join(output_dir, "seqs")
    if os.path.exists(fasta_dir):
        for fasta_file in Path(fasta_dir).glob("*.fa"):
            with open(fasta_file) as f:
                current_seq = []
                for line in f:
                    if line.startswith(">"):
                        if current_seq:
                            sequences.append(''.join(current_seq))
                            current_seq = []
                    else:
                        current_seq.append(line.strip())
                if current_seq:
                    sequences.append(''.join(current_seq))

    return sequences


def estimate_blast_identity(novel_seq: str, reference_seqs: list[str]) -> float:
    """
    Estimate max pairwise identity between novel_seq and reference_seqs.
    Simple k-mer based estimate (faster than real BLAST for prototyping).
    """
    if not reference_seqs:
        return 0.0
    k = 5
    novel_kmers = set(novel_seq[i:i+k] for i in range(len(novel_seq) - k + 1))
    max_identity = 0.0
    for ref in reference_seqs:
        ref_kmers = set(ref[i:i+k] for i in range(len(ref) - k + 1))
        if not ref_kmers:
            continue
        identity = len(novel_kmers & ref_kmers) / len(novel_kmers | ref_kmers)
        max_identity = max(max_identity, identity)
    return max_identity


def generate_variants_dataset(n_seqs: int = 50, output_path: str = "data/mpnn_variants.json",
                               mpnn_dir: str = "ProteinMPNN", seed: int = 42) -> dict:
    """
    Main function: generate ProteinMPNN variants for dangerous and benign structures,
    back-translate to DNA, compute BLAST identity estimates, save results.
    """
    random.seed(seed)
    np.random.seed(seed)

    results = {
        "dangerous": [],
        "benign": [],
        "summary": {},
    }

    reference_seqs_by_target = {}

    for structures, label_str, label_int in [
        (DANGEROUS_STRUCTURES, "dangerous", 1),
        (BENIGN_STRUCTURES, "benign", 0),
    ]:
        print(f"\n{'='*50}")
        print(f"Processing {label_str} structures...")
        print(f"{'='*50}")

        for pdb_id, chain, description in structures:
            print(f"\n  {pdb_id} ({description})")

            # Download PDB
            pdb_path = download_pdb(pdb_id)
            if pdb_path is None:
                print(f"  Skipping {pdb_id} (download failed)")
                continue

            # Run ProteinMPNN
            print(f"  Running ProteinMPNN (n={n_seqs}, temp=0.1)...")
            protein_seqs = run_proteinmpnn(pdb_path, chain, n_seqs=n_seqs, mpnn_dir=mpnn_dir)

            if not protein_seqs:
                print(f"  No sequences generated, skipping.")
                continue

            print(f"  Generated {len(protein_seqs)} protein sequences")

            # Keep reference sequences for BLAST identity estimation
            reference_seqs_by_target[pdb_id] = protein_seqs[:3]  # First few as "known"

            # Back-translate to DNA using both human and E. coli codon tables
            for i, prot_seq in enumerate(protein_seqs):
                # Human codon table (primary)
                dna_human = protein_to_dna(prot_seq, HUMAN_CODON_TABLE, seed=seed + i)
                # E. coli codon table (secondary variant)
                dna_ecoli = protein_to_dna(prot_seq, ECOLI_CODON_TABLE, seed=seed + i + 1000)

                # Estimate BLAST identity to known reference seqs
                known_refs = reference_seqs_by_target.get(pdb_id, [])
                blast_est = estimate_blast_identity(prot_seq, known_refs[:2]) if known_refs else 0.0

                entry = {
                    "pdb_id": pdb_id,
                    "chain": chain,
                    "description": description,
                    "label": label_int,
                    "protein_sequence": prot_seq,
                    "dna_human_optimized": dna_human,
                    "dna_ecoli_optimized": dna_ecoli,
                    "blast_identity_estimate": round(blast_est, 3),
                    "sequence_length_aa": len(prot_seq),
                    "sequence_length_dna": len(dna_human),
                }
                results[label_str].append(entry)

            print(f"  {len(protein_seqs)} variants generated for {pdb_id}")

    # Summary statistics
    n_dangerous = len(results["dangerous"])
    n_benign = len(results["benign"])

    if n_dangerous > 0:
        blast_ids = [e["blast_identity_estimate"] for e in results["dangerous"]]
        low_blast = sum(1 for x in blast_ids if x < 0.5)
        results["summary"] = {
            "n_dangerous_variants": n_dangerous,
            "n_benign_variants": n_benign,
            "dangerous_blast_id_mean": round(np.mean(blast_ids), 3) if blast_ids else 0,
            "dangerous_blast_id_lt_50pct": low_blast,
            "pct_below_blast_threshold": round(100 * low_blast / n_dangerous, 1) if n_dangerous else 0,
        }

    # Save
    os.makedirs(Path(output_path).parent, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*50}")
    print(f"Results saved to {output_path}")
    print(json.dumps(results["summary"], indent=2))
    print(f"{'='*50}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n_seqs", type=int, default=50)
    parser.add_argument("--output", default="data/mpnn_variants.json")
    parser.add_argument("--mpnn_dir", default="ProteinMPNN")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    generate_variants_dataset(
        n_seqs=args.n_seqs,
        output_path=args.output,
        mpnn_dir=args.mpnn_dir,
        seed=args.seed,
    )
