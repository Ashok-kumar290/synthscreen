---
language: en
license: apache-2.0
tags:
  - biosecurity
  - protein
  - esm2
  - lora
  - sequence-classification
  - synthguard
  - transformers
base_model: facebook/esm2_t33_650M_UR50D
datasets:
  - Seyomi/synthscreen-dataset
metrics:
  - auroc
  - recall
---

# SynthGuard ESM-2 — Protein Biosecurity Screening Model

Part of **SynthGuard**, a dual-track biosecurity screening system built for AIxBio Hackathon 2026 (Track 1: DNA Screening & Synthesis Controls).

## What it does

Screens protein sequences (translated from DNA) for biosecurity hazards at the amino acid level. Operates **independently of the DNA k-mer track** — providing an orthogonal signal that makes the system harder to evade. An adversary who games the DNA model's codon-usage patterns still produces a protein sequence that ESM-2 evaluates independently.

## Model architecture

Fine-tuned from [`facebook/esm2_t33_650M_UR50D`](https://huggingface.co/facebook/esm2_t33_650M_UR50D) (650M parameters) using LoRA:

- **LoRA config:** r=16, α=32, targets `query`, `key`, `value` attention projections, `modules_to_save=["classifier"]`
- **Trainable parameters:** 5.7M / 656M (0.87%)
- **Loss:** Focal loss (γ=2.0, α=0.75) to handle class imbalance
- **Hard example mining:** 2 rounds — false negatives with prob <0.6 re-weighted after each epoch
- **Sampling:** WeightedRandomSampler for balanced batches
- **Weights:** Merged via `merge_and_unload()` — no PEFT dependency at inference

## Translation

DNA sequences are translated using the best reading frame strategy: all 3 frames are tried, the longest ORF (truncated at first stop codon) is kept. Sequences producing <30 amino acids are excluded.

## Performance

Evaluated on held-out test set (15% of ~14,700 sequences):

| Metric | Value |
|--------|-------|
| AI-variant Recall | **89.6%** |
| Full-set Recall | 88.3% |
| AUROC | **0.916** |
| F1 | 0.835 |
| FPR (benign flagged) | 28.8% |
| BLAST baseline recall | 0.4% |

Note: Higher FPR than the k-mer model. The two tracks are designed to be used together — k-mer for fast triage, ESM-2 for confirmation on flagged sequences.

## Training data

Dataset: [`Seyomi/synthscreen-dataset`](https://huggingface.co/datasets/Seyomi/synthscreen-dataset)

Same dataset as the k-mer model, filtered to sequences that yield ≥30 amino acids after best-frame translation. Includes:
- Original hazardous protein sequences (20 families)
- Codon-shuffled DNA variants translated to protein
- ProteinMPNN-generated analogs of dangerous protein structures

## Usage

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

model = AutoModelForSequenceClassification.from_pretrained("Seyomi/synthguard-esm2")
tokenizer = AutoTokenizer.from_pretrained("facebook/esm2_t33_650M_UR50D")
model.eval()

def screen_protein(aa_seq, threshold=0.5):
    inputs = tokenizer(aa_seq, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits
    prob = torch.softmax(logits, dim=-1)[0, 1].item()
    return "HAZARDOUS" if prob >= threshold else "BENIGN", prob

# Example: translate DNA first
def translate_best_frame(dna):
    AA_TABLE = {
        'TTT':'F','TTC':'F','TTA':'L','TTG':'L','CTT':'L','CTC':'L','CTA':'L','CTG':'L',
        'ATT':'I','ATC':'I','ATA':'I','ATG':'M','GTT':'V','GTC':'V','GTA':'V','GTG':'V',
        'TCT':'S','TCC':'S','TCA':'S','TCG':'S','CCT':'P','CCC':'P','CCA':'P','CCG':'P',
        'ACT':'T','ACC':'T','ACA':'T','ACG':'T','GCT':'A','GCC':'A','GCA':'A','GCG':'A',
        'TAT':'Y','TAC':'Y','TAA':'*','TAG':'*','CAT':'H','CAC':'H','CAA':'Q','CAG':'Q',
        'AAT':'N','AAC':'N','AAA':'K','AAG':'K','GAT':'D','GAC':'D','GAA':'E','GAG':'E',
        'TGT':'C','TGC':'C','TGA':'*','TGG':'W','CGT':'R','CGC':'R','CGA':'R','CGG':'R',
        'AGT':'S','AGC':'S','AGA':'R','AGG':'R','GGT':'G','GGC':'G','GGA':'G','GGG':'G',
    }
    best = ""
    for frame in range(3):
        aa = "".join(AA_TABLE.get(dna[i:i+3], "X") for i in range(frame, len(dna)-2, 3))
        if "*" in aa:
            aa = aa[:aa.index("*")]
        if len(aa) > len(best):
            best = aa
    return best

dna = "ATGGCAAGCATGACGGGGGGACAACAGATTGGG..."
protein = translate_best_frame(dna)
decision, score = screen_protein(protein)
print(f"{decision} (score: {score:.3f})")
```

## Repository files

```
config.json                  # Model config (ESM-2 650M, num_labels=2)
model.safetensors            # Merged LoRA weights (no PEFT required)
tokenizer_config.json
special_tokens_map.json
vocab.txt
```

## Why a protein track alongside DNA?

Two orthogonal signals make the system harder to evade:
- The **DNA k-mer model** detects codon-usage bias at the nucleotide level
- The **ESM-2 model** detects functional protein patterns at the amino acid level

An adversary optimizing DNA sequence to avoid the k-mer signature still produces a protein that ESM-2 evaluates independently. Model disagreement (one flags, one doesn't) is itself a risk signal.

## Limitations

- Higher FPR (28.8%) than the k-mer model — use as confirmation layer, not primary triage
- Requires translatable sequences (≥30aa after best-frame translation)
- Short DNA fragments (<90bp) rarely produce usable translations
- Training used sequences from 20 hazardous families — novel protein folds outside this distribution may be missed

## Related

- DNA track: [`Seyomi/synthguard-kmer`](https://huggingface.co/Seyomi/synthguard-kmer)
- Dataset: [`Seyomi/synthscreen-dataset`](https://huggingface.co/datasets/Seyomi/synthscreen-dataset)
- Demo: [`Seyomi/synthguard-demo`](https://huggingface.co/spaces/Seyomi/synthguard-demo)
- Code: [github.com/Ashok-kumar290/synthscreen](https://github.com/Ashok-kumar290/synthscreen)

## Citation

```
SynthGuard: Closing the AI Biodesign Gap in DNA Synthesis Screening
AIxBio Hackathon 2026 — Track 1
Ashok Kumar
https://github.com/Ashok-kumar290/synthscreen
```
