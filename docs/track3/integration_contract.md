# BioLens — Synthscreen Integration Contract

This document defines the stable interface between BioLens (Track 3) and Synthscreen (Track 1).

---

## Design Rule

Only one module changes during Synthscreen integration:

```
services/model_interface.py
```

All other BioLens code (pages, storage, export, UI) remains unchanged.

---

## Function Signature

```python
def screen_sequence(sequence: str, seq_type: str) -> dict:
```

### Parameters

| Parameter | Type | Values | Description |
|-----------|------|--------|-------------|
| `sequence` | `str` | Raw nucleotide or amino acid string | Input sequence (whitespace stripped, uppercased internally) |
| `seq_type` | `str` | `"DNA"` or `"PROTEIN"` | Sequence alphabet to validate against |

### Return Value

```python
{
    "ok": bool,
    "hazard_score": float | None,       # 0.0 to 1.0, normalized
    "risk_level": str | None,           # "SAFE" | "REVIEW" | "HIGH"
    "model_hazard_score": float | None, # Raw model score before intelligence adjustment
    "model_risk_level": str | None,     # Raw model tier before intelligence adjustment
    "intel_modifier": float | None,     # Watchlist-driven score adjustment
    "effective_hazard_score": float | None, # Intelligence-adjusted operational score
    "effective_risk_level": str | None, # Intelligence-adjusted operational tier
    "confidence": float | None,         # 0.0 to 1.0, normalized
    "category": str | None,             # Predicted functional category
    "explanation": str | None,          # Short, readable reasoning
    "baseline_result": str | None,      # Optional baseline comparison text
    "model_name": str,                  # Audit-visible model identifier
    "data_source": str,                 # Provenance: "synthguard-api" | "biolens-heuristic" | "biolens-mock"
    "error": str | None                 # Machine-readable error when ok=False
}
```

---

## Field Semantics

### `ok`

- `True` → screening completed successfully, all result fields are populated
- `False` → screening failed, `error` contains the reason, result fields are `None`

### `hazard_score`

- Normalized float in `[0.0, 1.0]`
- Used for sorting, analytics, and operational risk tier assignment
- Higher values indicate higher concern
- When intelligence context matches, this mirrors `effective_hazard_score`; raw model output is preserved in `model_hazard_score`

### `risk_level`

Must be one of:

| Value | Meaning |
|-------|---------|
| `SAFE` | Low-concern functional profile |
| `REVIEW` | Ambiguous signal requiring analyst review |
| `HIGH` | Elevated concern, should be escalated |

Operational thresholds:
- `hazard_score >= 0.60` → `HIGH`
- `hazard_score >= 0.30` → `REVIEW`
- `hazard_score < 0.30` → `SAFE`

### `confidence`

- Normalized float in `[0.0, 1.0]`
- Represents the adapter's confidence in the hazard assessment
- Displayed in review and analytics views

### `category`

- Short label describing the predicted functional profile
- Examples: `"Routine metabolic gene signature"`, `"Elevated host-interaction signature"`

### `explanation`

- Human-readable explanation suitable for operator workflows
- Should be 1–2 sentences

### `baseline_result`

- Optional free-text comparison with conventional screening (e.g., BLAST)
- Can be `None` if no baseline comparison is available

### `model_name`

- String identifier for auditing purposes
- Format in mock mode: `"biolens-mock-adapter"`, `"biolens-demo-adapter"`
- Format in integrated mode: whatever the Synthscreen endpoint returns, or `"biolens-heuristic"` for protein sequences.

### `data_source`

- Provenance label for UI rendering and transparency
- `"synthguard-api"` for results from the live Track 1 model
- `"biolens-heuristic"` for results from the local BioLens engine (used for Protein sequences)
- `"biolens-mock"` or `"biolens-demo"` for simulated data
- `"unknown"` or `"biolens-config"` for errors originating before screening

### `error`

- `None` when `ok=True`
- Machine-readable error code when `ok=False`
- Examples: `"empty_sequence_input"`, `"invalid_dna_characters:XZ"`, `"integration_http_error:500"`

---

## Validation Rules

The adapter validates inputs before processing:

| Check | Error Code |
|-------|------------|
| Empty or whitespace-only sequence | `empty_sequence_input` |
| `seq_type` not `"DNA"` or `"PROTEIN"` | `unsupported_sequence_type` |
| Characters outside expected alphabet | `invalid_dna_characters:<chars>` or `invalid_protein_characters:<chars>` |

**Alphabets:**
- DNA: `A C G T N`
- Protein: `A B C D E F G H I K L M N P Q R S T V W X Y Z *`

---

## Integrated Mode

When `BIOLENS_MODE=integrated`, BioLens uses a **dual-engine architecture**:
1. **DNA** requests are routed via POST to `SYNTHSCREEN_ENDPOINT`.
2. **Protein** requests transparently fall back to the BioLens local heuristic engine, since the Track 1 SynthGuard API only supports DNA k-mer scoring.

### DNA Request (to API)

```http
POST <SYNTHSCREEN_ENDPOINT>
Content-Type: application/json

{
    "sequence": "<normalized_sequence>",
    "seq_type": "DNA" | "PROTEIN"
}
```

### Expected Response

The Synthscreen endpoint must return a JSON body conforming to the same return value schema above. The adapter coerces and validates the response before passing it to BioLens pages.

### Error Handling

| Scenario | Error Code |
|----------|------------|
| Timeout on HF Space cold start | `integration_timeout_error:<message>` |
| HTTP error response | `integration_http_error:<status_code>` |
| Connection failure | `integration_connection_error:<reason>` |
| Parse error | `integration_parse_error:<detail>` |
| Invalid response fields | `invalid_integrated_response:<detail>` |

---

## Mock Mode Behavior

In mock mode, the adapter computes a deterministic hazard score based on:

**DNA sequences:**
- Sequence length
- GC content deviation from 50%
- Motif hits (`ATG`, `TATA`, `CGCG`, `GGG`)
- Repeat run length
- Unknown base (`N`) fraction
- Hash-based variance for reproducibility

**Protein sequences:**
- Sequence length
- Hydrophobic fraction deviation
- Charged residue fraction deviation
- Dipeptide motif hits (`KK`, `RR`, `KR`, `GP`, `GG`)
- Low-complexity score
- Repeat run length
- Hash-based variance

Mock responses are fully deterministic: the same sequence and type always produce the same result.

---

## Integration Checklist

When connecting to a real Synthscreen backend:

- [ ] Set `BIOLENS_MODE=integrated`
- [ ] Set `SYNTHSCREEN_ENDPOINT` to the inference API URL
- [ ] Verify the endpoint returns a valid contract response (all required fields)
- [ ] Confirm `hazard_score` and `confidence` are in `[0.0, 1.0]`
- [ ] Confirm `risk_level` is one of `SAFE`, `REVIEW`, `HIGH`
- [ ] Test with representative DNA and protein sequences
- [ ] Verify error responses propagate correctly (non-200 status, timeout, invalid JSON)
- [ ] No changes needed to pages, storage, export, or UI code
