# SynthGuard: Protein & DNA Screening Engine (Track 1)

SynthGuard is a lightweight, function-aware biosecurity screening backend targeting the two critical gaps in existing synthesis controls: **AI-designed protein variants** that evade similarity-only detection, and **short-sequence false positives** that inflate manual review burden.

It complements established tools (SecureDNA, IBBIS commec, BLAST) rather than replacing them — adding an ML triage layer that combines k-mer evidence, ESM-2 embeddings, and explainable risk scoring.

---

## Performance Summary

| Metric | SynthGuard | BLAST Baseline |
|--------|-----------|---------------|
| Hazard Detection — Novel Variants | **98%** | ~62% |
| Chimeric Sequence Resistance | **86%** | 48% |
| AI-Redesigned Sequence Detection | **84%** | ~41% |

*Evaluated on a held-out benchmark including chimeric and AI-redesigned hazardous protein sequences.*

---

## Models

### Protein Track — ESM-2 650M + PEFT (LoRA)

ESM-2 is pre-trained on 250 million protein sequences and captures biological grammar, not just sequence similarity. LoRA fine-tuning adds hazard detection with only ~0.5% new parameters.

**Hardening techniques used:**
- **Focal Loss (γ=2.0)** — down-weights easy examples, focuses training on hard decision boundaries
- **Hard Example Mining** — failures collected after each round, oversampled 3× in the next
- **Contrastive Learning** — pulls hazardous/benign embeddings apart in representation space
- **Overfitting Guard** — training halts when train/val loss gap exceeds 10%

### DNA Track — K-mer Random Forest

A 5 MB deterministic triage model that provides high-throughput pre-screening for DNA sequences before more expensive protein-level analysis.

**Features used:**
- Sequence length, GC content, A/C/G/T/N ratio
- K-mer frequencies (k = 3–6)
- Low-complexity score, repeated motifs

---

## Directory Structure

```
funcscreen/
├── scripts/
│   └── training/
│       ├── train_esm2.py          # ESM-2 LoRA fine-tuning (8-bit QLoRA)
│       ├── train_kmer_robust.py   # K-mer Random Forest with robust cross-validation
│       └── train_v4_robust.py     # v4 pipeline: focal loss + hard example mining
├── configs/
│   ├── esm2_v4.json               # Base ESM-2 training config
│   └── esm2_v4.1_augmented.json   # Augmented config with hard mining + contrastive loss
└── report/
    └── funcscreen-report.md       # Full technical research report
```

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the v4 robust protein training pipeline
python scripts/training/train_v4_robust.py \
    --config configs/esm2_v4.1_augmented.json

# Run base ESM-2 LoRA fine-tuning
python scripts/training/train_esm2.py \
    --dataset data/processed/funcscreen_protein_dataset \
    --output models/esm2_lora \
    --epochs 5 \
    --use_8bit

# Run K-mer DNA triage model training
python scripts/training/train_kmer_robust.py \
    --data data/processed/dna_dataset \
    --output models/kmer_rf
```

---

## Output Format

Every screened sequence receives a structured risk decision:

```json
{
  "sequence_type": "protein",
  "risk_score": 0.87,
  "decision": "escalate",
  "evidence": [
    "ESM-2 embedding: nearest-neighbor class = toxin",
    "k-mer profile matches flagged cluster",
    "chimeric motif detected at positions 42–67",
    "low similarity to known sequences — function-based flag"
  ]
}
```

---

## Integration with BioLens (Track 3)

The BioLens dashboard calls SynthGuard via `services/model_interface.py`. In `integrated` mode, it sends sequences to the SynthGuard API endpoint and renders the structured risk output — evidence, score, and decision — directly in the analyst review interface.

See [`docs/track3/integration_contract.md`](../track3/integration_contract.md) for the full adapter interface specification.

---

## Relation to Existing Tools

| Tool | Approach | Gap SynthGuard Addresses |
|------|----------|--------------------------|
| SecureDNA | Privacy-preserving similarity search | AI-designed variants with weak similarity |
| IBBIS commec | HMM profiles, best above 150 bp | Short-sequence false positives |
| BLAST/MMseqs | Sequence similarity | Functionally equivalent but dissimilar variants |
| **SynthGuard** | ESM-2 embeddings + k-mer ML triage | All three gaps above, complementary layer |
