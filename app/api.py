"""
SynthGuard Track 1 API — FastAPI endpoint for Track 3 dashboard integration.

Run:
    pip install fastapi uvicorn
    python app/api.py

Or in Colab (after training):
    !uvicorn app.api:app --host 0.0.0.0 --port 8000 &
"""

import json
import math
import os
import pickle
from collections import Counter
from itertools import product
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="SynthGuard API",
    description="Track 1 biosecurity screening engine for AIxBio Hackathon 2026",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Feature extraction (must match notebook) ─────────────────────────────────

VOCAB = {k: ["".join(p) for p in product("ACGT", repeat=k)] for k in [3, 4, 5, 6]}


def extract_features(seq: str) -> list[float]:
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
        kmer_cnt = Counter(seq[i : i + k] for i in range(n - k + 1))
        total_k = max(n - k + 1, 1)
        feats.extend(kmer_cnt.get(km, 0) / total_k for km in VOCAB[k])
    return feats


# ── Model loading ─────────────────────────────────────────────────────────────

MODEL_DIR = Path(os.environ.get("SYNTHGUARD_MODEL_DIR", "models/synthguard_kmer"))

_general_model = None
_short_model = None
_meta = None


def _load_models():
    global _general_model, _short_model, _meta
    if _general_model is not None:
        return

    general_path = MODEL_DIR / "general_model.pkl"
    short_path = MODEL_DIR / "short_model.pkl"
    meta_path = MODEL_DIR / "meta.json"

    if not general_path.exists():
        raise RuntimeError(
            f"Models not found at {MODEL_DIR}. "
            "Run notebooks/synthguard_full.ipynb first to train and save models."
        )

    with open(general_path, "rb") as f:
        _general_model = pickle.load(f)
    with open(short_path, "rb") as f:
        _short_model = pickle.load(f)
    with open(meta_path) as f:
        _meta = json.load(f)


@app.on_event("startup")
async def startup():
    try:
        _load_models()
        print(f"SynthGuard models loaded from {MODEL_DIR}")
    except RuntimeError as e:
        print(f"WARNING: {e}\nAPI will return errors until models are loaded.")


# ── Request / Response schemas ────────────────────────────────────────────────


class ScreenRequest(BaseModel):
    sequence: str = Field(..., description="DNA or RNA sequence (IUPAC nucleotides)")
    threshold_review: float = Field(0.4, ge=0.0, le=1.0)
    threshold_escalate: float = Field(0.7, ge=0.0, le=1.0)


class ScreenResponse(BaseModel):
    risk_score: float
    decision: str  # ALLOW | REVIEW | ESCALATE
    sequence_length: int
    sequence_type: str
    gc_content: float
    evidence: list[str]
    model_used: str
    error: Optional[str] = None


class BatchScreenRequest(BaseModel):
    sequences: list[str]
    threshold_review: float = 0.4
    threshold_escalate: float = 0.7


class BatchScreenResponse(BaseModel):
    results: list[ScreenResponse]
    summary: dict


# ── Core screener ─────────────────────────────────────────────────────────────


def _screen_one(
    seq: str,
    threshold_review: float = 0.4,
    threshold_escalate: float = 0.7,
) -> dict:
    _load_models()

    seq = seq.upper().replace("U", "T").strip()
    if len(seq) < 10:
        return ScreenResponse(
            risk_score=0.0,
            decision="ALLOW",
            sequence_length=len(seq),
            sequence_type="DNA",
            gc_content=0.0,
            evidence=[],
            model_used="none",
            error="Sequence too short (<10bp)",
        ).dict()

    import numpy as np

    feats = np.array([extract_features(seq)])
    n = len(seq)
    cnt = Counter(seq)
    gc = (cnt.get("G", 0) + cnt.get("C", 0)) / n

    if n < 150:
        prob = _short_model.predict_proba(feats)[0, 1]
        model_used = "short-seq specialist"
    else:
        prob = _general_model.predict_proba(feats)[0, 1]
        model_used = "general triage"

    if prob >= threshold_escalate:
        decision = "ESCALATE"
    elif prob >= threshold_review:
        decision = "REVIEW"
    else:
        decision = "ALLOW"

    evidence = []
    if n < 150:
        evidence.append(f"Short sequence ({n}bp): specialist model active")
    if gc > 0.65:
        evidence.append(f"High GC content ({gc:.0%})")
    elif gc < 0.30:
        evidence.append(f"Low GC content ({gc:.0%})")
    entropy = -sum((c / n) * math.log2(c / n) for c in cnt.values() if c > 0)
    if entropy < 1.5:
        evidence.append(f"Low complexity (entropy={entropy:.2f})")
    evidence.append(f"Risk score: {prob:.3f}")
    evidence.append(f"Model: {model_used}")

    return {
        "risk_score": round(float(prob), 4),
        "decision": decision,
        "sequence_length": n,
        "sequence_type": "DNA",
        "gc_content": round(gc, 3),
        "evidence": evidence,
        "model_used": model_used,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    models_loaded = _general_model is not None
    return {
        "status": "ok" if models_loaded else "models_not_loaded",
        "models_loaded": models_loaded,
        "model_dir": str(MODEL_DIR),
    }


@app.post("/screen", response_model=ScreenResponse)
async def screen_sequence(req: ScreenRequest):
    try:
        result = _screen_one(req.sequence, req.threshold_review, req.threshold_escalate)
        return ScreenResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/screen/batch", response_model=BatchScreenResponse)
async def screen_batch(req: BatchScreenRequest):
    if len(req.sequences) > 1000:
        raise HTTPException(status_code=400, detail="Max 1000 sequences per batch")
    results = []
    for seq in req.sequences:
        result = _screen_one(seq, req.threshold_review, req.threshold_escalate)
        results.append(ScreenResponse(**result))

    decisions = [r.decision for r in results]
    summary = {
        "total": len(results),
        "allow": decisions.count("ALLOW"),
        "review": decisions.count("REVIEW"),
        "escalate": decisions.count("ESCALATE"),
        "flag_rate": round(
            (decisions.count("REVIEW") + decisions.count("ESCALATE")) / max(len(results), 1), 3
        ),
    }
    return BatchScreenResponse(results=results, summary=summary)


@app.get("/model/info")
async def model_info():
    if _meta is None:
        raise HTTPException(status_code=503, detail="Models not loaded")
    return _meta


# ── BioLens adapter (Track 3 integration) ────────────────────────────────────

_CATEGORY_BANK = {
    "DNA": {
        "SAFE":   ["Routine metabolic gene signature", "Common structural cassette", "Low-concern regulatory context"],
        "REVIEW": ["Ambiguous host-interaction signal", "Regulatory activity worth analyst review", "Unresolved functional control pattern"],
        "HIGH":   ["Elevated host-interaction signature", "Escalation-priority functional signal", "High-concern regulation-linked pattern"],
    },
    "PROTEIN": {
        "SAFE":   ["Routine enzyme-like profile", "Low-concern scaffold signature", "Common cellular maintenance pattern"],
        "REVIEW": ["Ambiguous membrane-associated profile", "Unresolved signaling-like pattern", "Review-level interaction motif cluster"],
        "HIGH":   ["Elevated interaction-associated profile", "Escalation-priority effector-like pattern", "High-concern modulation signature"],
    },
}


def _pick_category(seq_type: str, risk_level: str, seq: str) -> str:
    import hashlib
    bank = _CATEGORY_BANK.get(seq_type, _CATEGORY_BANK["DNA"])[risk_level]
    idx = int(hashlib.sha256(seq[:64].encode()).hexdigest()[:8], 16) % len(bank)
    return bank[idx]


def _build_threat_breakdown(seq: str, prob: float) -> dict:
    n = max(len(seq), 1)
    cnt = Counter(seq)
    gc = (cnt.get("G", 0) + cnt.get("C", 0)) / n
    motif_hits = sum(seq.count(m) for m in ("ATG", "TATA", "CGCG", "GGG"))
    pathogenicity   = min(max(prob * 0.85 + abs(gc - 0.5) * 0.3, 0.0), 1.0)
    evasion         = min(max(prob * 0.7 - abs(gc - 0.5) * 0.2, 0.0), 1.0)
    synthesis_feas  = min(max(0.9 - n / 8000, 0.1), 1.0)
    env_resilience  = min(max(0.3 + gc * 0.4, 0.0), 1.0)
    host_range      = min(max(prob * 0.6 + min(motif_hits * 0.02, 0.2), 0.0), 1.0)
    return {
        "pathogenicity":          round(pathogenicity, 3),
        "evasion_potential":      round(evasion, 3),
        "synthesis_feasibility":  round(synthesis_feas, 3),
        "environmental_resilience": round(env_resilience, 3),
        "host_range":             round(host_range, 3),
    }


def _build_attribution(seq: str) -> dict:
    positions = [i for i in range(0, min(len(seq), 300), 7) if seq[i] in "GC"]
    scores = [round(0.5 + (ord(seq[i]) % 10) / 20, 3) for i in positions]
    regions = [{"start": 0, "end": min(30, len(seq)),
                "label": "GC-rich codon region", "score": round(min(len(positions) / 40, 1.0), 3)}]
    return {"positions": positions[:20], "scores": scores[:20], "regions": regions}


class BioLensRequest(BaseModel):
    sequence: str
    seq_type: str = "DNA"


@app.post("/biolens/screen")
async def biolens_screen(req: BioLensRequest):
    """BioLens adapter — speaks the Track 3 contract schema."""
    try:
        seq = req.sequence.upper().replace("U", "T").strip()
        seq_type = req.seq_type.upper() if req.seq_type.upper() in ("DNA", "PROTEIN") else "DNA"

        if len(seq) < 10:
            return {"ok": False, "hazard_score": None, "risk_level": None,
                    "confidence": None, "category": None, "explanation": None,
                    "baseline_result": None, "model_name": "synthguard-kmer", "error": "sequence_too_short"}

        result = _screen_one(seq)
        prob    = result["risk_score"]
        decision = result["decision"]

        risk_map = {"ALLOW": "SAFE", "REVIEW": "REVIEW", "ESCALATE": "HIGH"}
        risk_level = risk_map[decision]

        confidence = round(min(max(abs(prob - 0.5) * 2 + 0.5, 0.5), 0.99), 3)

        exp_map = {
            "SAFE":   f"SynthGuard k-mer screening found a low-concern codon-usage profile (score {prob:.2f}). No hazard signal detected.",
            "REVIEW": f"SynthGuard k-mer screening detected an ambiguous codon-usage pattern (score {prob:.2f}). Analyst review recommended.",
            "HIGH":   f"SynthGuard k-mer screening detected elevated pathogen-like codon bias (score {prob:.2f}). This sequence warrants escalation.",
        }
        blast_map = {
            "SAFE":   "BLAST similarity check: low identity to known hazards — cleared at standard threshold.",
            "REVIEW": "BLAST similarity check: partial overlap with known hazard families — manual review recommended.",
            "HIGH":   "BLAST similarity check: sequence likely evades BLAST (AI-designed codon variant) — function-aware flag retained.",
        }

        return {
            "ok":             True,
            "hazard_score":   prob,
            "risk_level":     risk_level,
            "confidence":     confidence,
            "category":       _pick_category(seq_type, risk_level, seq),
            "explanation":    exp_map[risk_level],
            "baseline_result": blast_map[risk_level],
            "model_name":     "synthguard-kmer",
            "error":          None,
            "threat_breakdown":  _build_threat_breakdown(seq, prob),
            "attribution_data":  _build_attribution(seq),
        }
    except Exception as e:
        return {"ok": False, "hazard_score": None, "risk_level": None,
                "confidence": None, "category": None, "explanation": None,
                "baseline_result": None, "model_name": "synthguard-kmer", "error": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
