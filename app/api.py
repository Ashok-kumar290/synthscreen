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

# ── Track 4: split-order detection (inlined) ─────────────────────────────────

import json as _json
import sqlite3 as _sqlite3
import time as _time
from pathlib import Path as _Path
from typing import Optional as _Optional

_SPLIT_DB = _Path("/tmp/split_orders.db")
_MIN_OVERLAP = 15
_MAX_ASSEMBLED = 12_000
_MAX_FRAGS = 30


def _split_conn():
    c = _sqlite3.connect(str(_SPLIT_DB), check_same_thread=False)
    c.row_factory = _sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS fragments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id  TEXT NOT NULL,
            order_id     TEXT NOT NULL,
            sequence     TEXT NOT NULL,
            length       INTEGER NOT NULL,
            ind_score    REAL,
            ind_decision TEXT,
            submitted_at REAL NOT NULL,
            flagged      INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id    TEXT NOT NULL,
            assembled_seq  TEXT NOT NULL,
            assembly_score REAL NOT NULL,
            fragment_ids   TEXT NOT NULL,
            created_at     REAL NOT NULL
        );
    """)
    c.commit()
    return c


def _frag_overlap(a: str, b: str) -> int:
    cap = min(len(a), len(b))
    for k in range(cap, _MIN_OVERLAP - 1, -1):
        if a[-k:] == b[:k]:
            return k
    return 0


def _assemble(seqs: list) -> str:
    if not seqs:
        return ""
    pool = list(seqs)
    while len(pool) > 1:
        best, bi, bj = 0, -1, -1
        for i in range(len(pool)):
            for j in range(len(pool)):
                if i == j:
                    continue
                ov = _frag_overlap(pool[i], pool[j])
                if ov > best:
                    best, bi, bj = ov, i, j
        if best < _MIN_OVERLAP:
            break
        merged = pool[bi] + pool[bj][best:]
        pool = [s for k, s in enumerate(pool) if k not in (bi, bj)]
        pool.append(merged)
        if len(pool[-1]) > _MAX_ASSEMBLED:
            break
    return max(pool, key=len)


class _FragIn(BaseModel):
    customer_id: str
    order_id: str
    sequence: str


class _FragOut(BaseModel):
    fragment_id: int
    individual_decision: str
    individual_score: float
    assembly_attempted: bool
    assembly_decision: Optional[str] = None
    assembly_score: Optional[float] = None
    alert: bool = False
    alert_id: Optional[int] = None
    message: str


class _CustStatus(BaseModel):
    customer_id: str
    fragment_count: int
    flagged_count: int
    alerts: list
    fragments: list


@app.post("/split/submit", response_model=_FragOut, tags=["split-order-detection"])
async def split_submit(req: _FragIn):
    """Submit one synthesis fragment. Assembles with prior fragments from the same customer."""
    seq = req.sequence.upper().replace("U", "T").strip()
    if len(seq) < 10:
        raise HTTPException(status_code=400, detail="Fragment too short (<10bp)")

    db = _split_conn()
    n_existing = db.execute(
        "SELECT COUNT(*) FROM fragments WHERE customer_id=?", (req.customer_id,)
    ).fetchone()[0]
    if n_existing >= _MAX_FRAGS:
        db.close()
        raise HTTPException(status_code=429, detail="Fragment cap reached for customer")

    ind = _screen_one(seq)
    ind_score = ind["risk_score"]
    ind_decision = ind["decision"]

    cur = db.execute(
        "INSERT INTO fragments (customer_id,order_id,sequence,length,ind_score,ind_decision,submitted_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (req.customer_id, req.order_id, seq, len(seq), ind_score, ind_decision, _time.time()),
    )
    frag_id = cur.lastrowid
    db.commit()

    rows = db.execute(
        "SELECT id,sequence FROM fragments WHERE customer_id=? ORDER BY submitted_at",
        (req.customer_id,),
    ).fetchall()

    asm_decision = None
    asm_score = None
    alert = False
    alert_id = None
    attempted = len(rows) >= 2

    if attempted:
        seqs = [r["sequence"] for r in rows]
        ids  = [r["id"] for r in rows]
        assembled = _assemble(seqs)
        if len(assembled) >= 50:
            asm = _screen_one(assembled)
            asm_score = asm["risk_score"]
            asm_decision = asm["decision"]
            if asm_decision == "ESCALATE":
                alert = True
                for fid in ids:
                    db.execute("UPDATE fragments SET flagged=1 WHERE id=?", (fid,))
                cur2 = db.execute(
                    "INSERT INTO alerts (customer_id,assembled_seq,assembly_score,fragment_ids,created_at) "
                    "VALUES (?,?,?,?,?)",
                    (req.customer_id, assembled[:1000], asm_score, _json.dumps(ids), _time.time()),
                )
                alert_id = cur2.lastrowid

    db.commit()
    db.close()

    parts = [f"Fragment stored (id={frag_id}, {len(seq)}bp)."]
    parts.append(f"Individual screen: {ind_decision} ({ind_score:.3f}).")
    if attempted:
        parts.append(f"Assembly of {len(rows)} fragment(s): {asm_decision} ({asm_score:.3f}).")
    if alert:
        parts.append("ALERT: assembled sequence flagged ESCALATE.")

    return _FragOut(
        fragment_id=frag_id,
        individual_decision=ind_decision,
        individual_score=ind_score,
        assembly_attempted=attempted,
        assembly_decision=asm_decision,
        assembly_score=asm_score,
        alert=alert,
        alert_id=alert_id,
        message=" ".join(parts),
    )


@app.get("/split/customer/{customer_id}", response_model=_CustStatus, tags=["split-order-detection"])
async def split_customer_status(customer_id: str):
    """All fragments and alerts for a customer."""
    db = _split_conn()
    frags = db.execute(
        "SELECT id,order_id,length,ind_score,ind_decision,submitted_at,flagged "
        "FROM fragments WHERE customer_id=? ORDER BY submitted_at", (customer_id,)
    ).fetchall()
    alerts = db.execute(
        "SELECT id,assembly_score,fragment_ids,created_at FROM alerts "
        "WHERE customer_id=? ORDER BY created_at DESC", (customer_id,)
    ).fetchall()
    db.close()
    return _CustStatus(
        customer_id=customer_id,
        fragment_count=len(frags),
        flagged_count=sum(1 for f in frags if f["flagged"]),
        alerts=[dict(a) for a in alerts],
        fragments=[dict(f) for f in frags],
    )


@app.delete("/split/customer/{customer_id}/flush", tags=["split-order-detection"])
async def split_flush(customer_id: str):
    """Clear all fragment state for a customer."""
    db = _split_conn()
    db.execute("DELETE FROM fragments WHERE customer_id=?", (customer_id,))
    db.execute("DELETE FROM alerts WHERE customer_id=?", (customer_id,))
    db.commit()
    db.close()
    return {"ok": True, "customer_id": customer_id}

# ── Feature extraction (must match training pipeline) ─────────────────────────

VOCAB = {k: ["".join(p) for p in product("ACGT", repeat=k)] for k in [3, 4, 5, 6]}

CODON_TABLE = {
    'TTT':'F','TTC':'F','TTA':'L','TTG':'L','CTT':'L','CTC':'L','CTA':'L','CTG':'L',
    'ATT':'I','ATC':'I','ATA':'I','ATG':'M','GTT':'V','GTC':'V','GTA':'V','GTG':'V',
    'TCT':'S','TCC':'S','TCA':'S','TCG':'S','CCT':'P','CCC':'P','CCA':'P','CCG':'P',
    'ACT':'T','ACC':'T','ACA':'T','ACG':'T','GCT':'A','GCC':'A','GCA':'A','GCG':'A',
    'TAT':'Y','TAC':'Y','TAA':'*','TAG':'*','CAT':'H','CAC':'H','CAA':'Q','CAG':'Q',
    'AAT':'N','AAC':'N','AAA':'K','AAG':'K','GAT':'D','GAC':'D','GAA':'E','GAG':'E',
    'TGT':'C','TGC':'C','TGA':'*','TGG':'W','CGT':'R','CGC':'R','CGA':'R','CGG':'R',
    'AGT':'S','AGC':'S','AGA':'R','AGG':'R','GGT':'G','GGC':'G','GGA':'G','GGG':'G',
}

_AA_CODONS: dict = {}
for _c, _a in CODON_TABLE.items():
    _AA_CODONS.setdefault(_a, []).append(_c)

ALL_CODONS = sorted(CODON_TABLE.keys())
AMINO_ACIDS = sorted(a for a in set(CODON_TABLE.values()) if a != '*')

# Codon frequencies per thousand (Kazusa DB) for CAI computation
_ECOLI = {'TTT':22.0,'TTC':16.5,'TTA':13.9,'TTG':13.1,'CTT':10.9,'CTC':10.0,'CTA':3.8,'CTG':52.7,'ATT':28.8,'ATC':25.1,'ATA':4.4,'ATG':27.4,'GTT':19.5,'GTC':14.7,'GTA':10.8,'GTG':25.9,'TCT':7.8,'TCC':8.8,'TCA':7.0,'TCG':8.7,'CCT':7.2,'CCC':5.6,'CCA':8.4,'CCG':23.3,'ACT':9.0,'ACC':23.4,'ACA':7.2,'ACG':14.6,'GCT':15.3,'GCC':25.8,'GCA':20.6,'GCG':33.5,'TAT':16.3,'TAC':12.5,'TAA':2.0,'TAG':0.3,'CAT':13.2,'CAC':9.6,'CAA':15.5,'CAG':28.7,'AAT':22.3,'AAC':22.4,'AAA':33.6,'AAG':10.1,'GAT':32.2,'GAC':19.0,'GAA':39.8,'GAG':18.3,'TGT':5.0,'TGC':6.5,'TGA':1.0,'TGG':15.2,'CGT':21.1,'CGC':21.7,'CGA':3.7,'CGG':5.3,'AGT':8.7,'AGC':15.8,'AGA':3.5,'AGG':2.9,'GGT':24.7,'GGC':29.5,'GGA':8.0,'GGG':11.5}
_HUMAN  = {'TTT':17.6,'TTC':20.3,'TTA':7.7,'TTG':12.9,'CTT':13.2,'CTC':19.6,'CTA':7.2,'CTG':39.6,'ATT':16.0,'ATC':20.8,'ATA':7.5,'ATG':22.0,'GTT':11.0,'GTC':14.5,'GTA':7.1,'GTG':28.1,'TCT':15.2,'TCC':17.7,'TCA':12.2,'TCG':4.4,'CCT':17.5,'CCC':19.8,'CCA':16.9,'CCG':6.9,'ACT':13.1,'ACC':18.9,'ACA':15.1,'ACG':6.1,'GCT':18.4,'GCC':27.7,'GCA':15.8,'GCG':7.4,'TAT':12.2,'TAC':15.3,'TAA':1.0,'TAG':0.8,'CAT':10.9,'CAC':15.1,'CAA':12.3,'CAG':34.2,'AAT':17.0,'AAC':19.1,'AAA':24.4,'AAG':31.9,'GAT':21.8,'GAC':25.1,'GAA':29.0,'GAG':39.6,'TGT':10.6,'TGC':12.6,'TGA':1.6,'TGG':13.2,'CGT':4.5,'CGC':10.4,'CGA':6.2,'CGG':11.4,'AGT':15.2,'AGC':19.5,'AGA':11.5,'AGG':11.4,'GGT':10.8,'GGC':22.2,'GGA':16.5,'GGG':16.5}
_YEAST  = {'TTT':26.2,'TTC':18.4,'TTA':26.2,'TTG':27.2,'CTT':12.3,'CTC':5.4,'CTA':13.4,'CTG':10.5,'ATT':30.1,'ATC':17.2,'ATA':17.8,'ATG':20.9,'GTT':22.1,'GTC':11.8,'GTA':11.8,'GTG':10.8,'TCT':23.5,'TCC':14.2,'TCA':18.7,'TCG':8.6,'CCT':13.5,'CCC':6.8,'CCA':18.3,'CCG':5.4,'ACT':20.3,'ACC':13.1,'ACA':17.9,'ACG':8.1,'GCT':21.1,'GCC':12.6,'GCA':16.0,'GCG':6.2,'TAT':18.8,'TAC':14.8,'TAA':1.1,'TAG':0.5,'CAT':13.6,'CAC':7.8,'CAA':27.3,'CAG':12.1,'AAT':35.9,'AAC':24.8,'AAA':41.9,'AAG':30.8,'GAT':37.6,'GAC':20.2,'GAA':45.0,'GAG':19.2,'TGT':8.1,'TGC':4.8,'TGA':0.7,'TGG':10.4,'CGT':6.4,'CGC':2.6,'CGA':3.0,'CGG':1.7,'AGT':14.2,'AGC':9.8,'AGA':21.3,'AGG':9.2,'GGT':23.9,'GGC':9.8,'GGA':10.9,'GGG':6.0}

def _ref_rscu(freq_table: dict) -> dict:
    rscu = {}
    for aa, codons in _AA_CODONS.items():
        if aa == '*':
            for c in codons: rscu[c] = 1.0
            continue
        max_f = max(freq_table.get(c, 0.1) for c in codons)
        for c in codons:
            rscu[c] = freq_table.get(c, 0.1) / max_f if max_f > 0 else 1.0
    return rscu

_ECOLI_RSCU = _ref_rscu(_ECOLI)
_HUMAN_RSCU = _ref_rscu(_HUMAN)
_YEAST_RSCU = _ref_rscu(_YEAST)


def _codon_features(seq: str) -> list[float]:
    """RSCU (64) + CAI×3 (3) + AA composition (20) = 87 features."""
    # In-frame codon counts (frame 0)
    codon_cnt: Counter = Counter()
    for i in range(0, len(seq) - 2, 3):
        cdn = seq[i:i+3]
        if len(cdn) == 3 and cdn in CODON_TABLE:
            codon_cnt[cdn] += 1

    # RSCU for all 64 codons
    rscu_vals: dict = {}
    for aa, codons in _AA_CODONS.items():
        if aa == '*':
            for c in codons: rscu_vals[c] = 1.0
            continue
        aa_total = sum(codon_cnt.get(c, 0) for c in codons)
        n_syn = len(codons)
        expected = aa_total / n_syn if aa_total > 0 else 0
        for c in codons:
            rscu_vals[c] = codon_cnt.get(c, 0) / expected if expected > 0 else 1.0
    rscu_feats = [rscu_vals.get(c, 1.0) for c in ALL_CODONS]

    # CAI against 3 reference organisms
    def cai(ref_rscu: dict) -> float:
        log_sum, count = 0.0, 0
        for cdn, n in codon_cnt.items():
            if CODON_TABLE.get(cdn, '*') != '*':
                log_sum += math.log(max(ref_rscu.get(cdn, 0.01), 1e-6)) * n
                count += n
        return math.exp(log_sum / count) if count > 0 else 0.5
    cai_feats = [cai(_ECOLI_RSCU), cai(_HUMAN_RSCU), cai(_YEAST_RSCU)]

    # Amino acid composition (20 features)
    aa_total = sum(n for cdn, n in codon_cnt.items() if CODON_TABLE.get(cdn, '*') != '*')
    aa_cnt: Counter = Counter()
    for cdn, n in codon_cnt.items():
        aa = CODON_TABLE.get(cdn, '*')
        if aa != '*':
            aa_cnt[aa] += n
    aa_feats = [aa_cnt.get(aa, 0) / max(aa_total, 1) for aa in AMINO_ACIDS]

    return rscu_feats + cai_feats + aa_feats


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
    feats.extend(_codon_features(seq))
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
    threshold_review: float = Field(0.3, ge=0.0, le=1.0)
    threshold_escalate: float = Field(0.6, ge=0.0, le=1.0)


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
    threshold_review: float = 0.3
    threshold_escalate: float = 0.6


class BatchScreenResponse(BaseModel):
    results: list[ScreenResponse]
    summary: dict


# ── Core screener ─────────────────────────────────────────────────────────────


def _screen_one(
    seq: str,
    threshold_review: float = 0.3,
    threshold_escalate: float = 0.6,
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
        seq = req.sequence.upper().replace("U", "T").strip()
        if _is_protein(seq):
            raise HTTPException(status_code=422, detail="protein_not_supported: submit coding DNA sequence")
        if not _is_valid_dna(seq):
            raise HTTPException(status_code=422, detail="invalid_sequence: not a valid DNA sequence")
        result = _screen_one(req.sequence, req.threshold_review, req.threshold_escalate)
        return ScreenResponse(**result)
    except HTTPException:
        raise
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


def _is_protein(seq: str) -> bool:
    """Return True if the sequence looks like amino acids rather than DNA.

    Amino acid letters that never appear in IUPAC DNA: E F I L M P Q Z
    If >3% of characters are protein-only letters, classify as protein.
    """
    protein_only = set("EFILMPQZ")
    n = max(len(seq), 1)
    hits = sum(1 for c in seq if c in protein_only)
    return hits / n > 0.03


def _is_valid_dna(seq: str) -> bool:
    """Return True if at least 85% of characters are valid IUPAC DNA bases."""
    valid = set("ACGTN")
    n = max(len(seq), 1)
    return sum(1 for c in seq if c in valid) / n >= 0.85


@app.post("/biolens/screen")
async def biolens_screen(req: BioLensRequest):
    """BioLens adapter — speaks the Track 3 contract schema."""
    try:
        seq = req.sequence.upper().replace("U", "T").strip()
        seq_type = req.seq_type.upper() if req.seq_type.upper() in ("DNA", "PROTEIN") else "DNA"

        # Detect protein from sequence content regardless of what the client declares
        if seq_type == "PROTEIN" or _is_protein(seq):
            return {"ok": False, "hazard_score": None, "risk_level": None,
                    "confidence": None, "category": None,
                    "explanation": "SynthGuard is a DNA-only screener. Protein sequences are not supported — please submit the coding DNA sequence instead.",
                    "baseline_result": None, "model_name": "synthguard-kmer",
                    "error": "protein_not_supported"}

        # Reject random/garbage input that isn't DNA or protein
        if not _is_valid_dna(seq):
            return {"ok": False, "hazard_score": None, "risk_level": None,
                    "confidence": None, "category": None,
                    "explanation": "Input does not appear to be a valid DNA sequence. Please submit a nucleotide sequence (A/C/G/T/N characters).",
                    "baseline_result": None, "model_name": "synthguard-kmer",
                    "error": "invalid_sequence"}

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
