"""
Track 4: Split-order detection.

Detects hazardous sequences ordered as multiple short fragments.
Each fragment individually passes SynthGuard screening, but the
assembled sequence is flagged.

Endpoints (mounted at /split):
  POST /split/submit                      — ingest one fragment
  GET  /split/customer/{customer_id}      — status for a customer
  DELETE /split/customer/{customer_id}/flush — clear customer state

Algorithm:
  1. Store each incoming fragment in SQLite (per customer_id)
  2. On each new submission, attempt greedy overlap assembly of all
     fragments from that customer
  3. Screen the assembled sequence with SynthGuard k-mer
  4. If assembled sequence scores ESCALATE, raise an alert and flag
     all contributing fragment IDs
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/split", tags=["split-order-detection"])

# SQLite persists across requests (ephemeral in HF Space but fine for demo)
_DB_PATH = Path("/tmp/split_orders.db")

MIN_OVERLAP_BP = 15     # minimum suffix/prefix overlap to merge two fragments
MAX_ASSEMBLED_BP = 12_000
MAX_FRAGS_PER_CUSTOMER = 30   # safety cap — prevents O(n²) blowup


# ── Database helpers ───────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS fragments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id     TEXT    NOT NULL,
            order_id        TEXT    NOT NULL,
            sequence        TEXT    NOT NULL,
            length          INTEGER NOT NULL,
            ind_score       REAL,
            ind_decision    TEXT,
            submitted_at    REAL    NOT NULL,
            flagged         INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id     TEXT    NOT NULL,
            assembled_seq   TEXT    NOT NULL,
            assembly_score  REAL    NOT NULL,
            fragment_ids    TEXT    NOT NULL,
            created_at      REAL    NOT NULL
        );
    """)
    c.commit()
    return c


# ── Overlap assembly ───────────────────────────────────────────────────────────

def _suffix_prefix_overlap(a: str, b: str) -> int:
    """Length of longest suffix of a that equals a prefix of b (>= MIN_OVERLAP_BP)."""
    cap = min(len(a), len(b))
    for k in range(cap, MIN_OVERLAP_BP - 1, -1):
        if a[-k:] == b[:k]:
            return k
    return 0


def _greedy_assemble(seqs: list[str]) -> str:
    """
    Greedy overlap-layout-consensus assembly.
    Repeatedly merges the pair with the largest overlap until no
    overlaps remain, then concatenates leftover contigs.
    Returns the longest contig produced.
    """
    if not seqs:
        return ""
    pool = list(seqs)
    while len(pool) > 1:
        best, bi, bj = 0, -1, -1
        for i in range(len(pool)):
            for j in range(len(pool)):
                if i == j:
                    continue
                ov = _suffix_prefix_overlap(pool[i], pool[j])
                if ov > best:
                    best, bi, bj = ov, i, j
        if best < MIN_OVERLAP_BP:
            break
        merged = pool[bi] + pool[bj][best:]
        pool = [s for k, s in enumerate(pool) if k not in (bi, bj)]
        pool.append(merged)
        if len(pool[-1]) > MAX_ASSEMBLED_BP:
            break
    return max(pool, key=len)


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class FragmentIn(BaseModel):
    customer_id: str = Field(..., description="Synthesis customer identifier")
    order_id: str = Field(..., description="Fragment-level order identifier")
    sequence: str = Field(..., description="DNA sequence of this fragment")


class FragmentOut(BaseModel):
    fragment_id: int
    individual_decision: str
    individual_score: float
    assembly_attempted: bool
    assembly_decision: Optional[str] = None
    assembly_score: Optional[float] = None
    alert: bool = False
    alert_id: Optional[int] = None
    message: str


class CustomerStatus(BaseModel):
    customer_id: str
    fragment_count: int
    flagged_count: int
    alerts: list[dict]
    fragments: list[dict]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/submit", response_model=FragmentOut, summary="Submit a synthesis fragment")
async def submit_fragment(req: FragmentIn):
    """
    Submit one fragment from a synthesis order.

    The fragment is screened individually and then assembled with all
    prior fragments from the same customer_id. If the assembly is
    flagged ESCALATE, an alert is raised and all contributing
    fragment IDs are marked flagged.
    """
    # Late import so this module can be imported before api.py has loaded models
    try:
        from api import _screen_one
    except ImportError:
        from app.api import _screen_one

    seq = req.sequence.upper().replace("U", "T").strip()
    if len(seq) < 10:
        raise HTTPException(status_code=400, detail="Fragment too short (<10bp)")

    db = _conn()

    # Cap fragments per customer
    n_existing = db.execute(
        "SELECT COUNT(*) FROM fragments WHERE customer_id=?",
        (req.customer_id,)
    ).fetchone()[0]
    if n_existing >= MAX_FRAGS_PER_CUSTOMER:
        db.close()
        raise HTTPException(
            status_code=429,
            detail=f"Fragment cap ({MAX_FRAGS_PER_CUSTOMER}) reached for customer '{req.customer_id}'"
        )

    # Individual screen
    ind = _screen_one(seq)
    ind_score = ind["risk_score"]
    ind_decision = ind["decision"]

    # Persist fragment
    cur = db.execute(
        "INSERT INTO fragments "
        "(customer_id, order_id, sequence, length, ind_score, ind_decision, submitted_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (req.customer_id, req.order_id, seq, len(seq), ind_score, ind_decision, time.time()),
    )
    frag_id = cur.lastrowid
    db.commit()

    # Load all fragments for this customer (including the one just stored)
    rows = db.execute(
        "SELECT id, sequence FROM fragments WHERE customer_id=? ORDER BY submitted_at",
        (req.customer_id,),
    ).fetchall()

    asm_decision = None
    asm_score = None
    alert = False
    alert_id = None
    attempted = len(rows) >= 2

    if attempted:
        seqs = [r["sequence"] for r in rows]
        ids = [r["id"] for r in rows]
        assembled = _greedy_assemble(seqs)

        if len(assembled) >= 50:
            asm = _screen_one(assembled)
            asm_score = asm["risk_score"]
            asm_decision = asm["decision"]

            if asm_decision == "ESCALATE":
                alert = True
                for fid in ids:
                    db.execute("UPDATE fragments SET flagged=1 WHERE id=?", (fid,))
                cur2 = db.execute(
                    "INSERT INTO alerts "
                    "(customer_id, assembled_seq, assembly_score, fragment_ids, created_at) "
                    "VALUES (?,?,?,?,?)",
                    (req.customer_id, assembled[:1000], asm_score,
                     json.dumps(ids), time.time()),
                )
                alert_id = cur2.lastrowid

    db.commit()
    db.close()

    parts = [f"Fragment stored (id={frag_id}, {len(seq)}bp)."]
    parts.append(f"Individual screen: {ind_decision} ({ind_score:.3f}).")
    if attempted:
        parts.append(
            f"Assembly of {len(rows)} fragment(s): "
            f"{asm_decision} ({asm_score:.3f})."
        )
    if alert:
        parts.append("ALERT: assembled sequence flagged ESCALATE.")

    return FragmentOut(
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


@router.get(
    "/customer/{customer_id}",
    response_model=CustomerStatus,
    summary="Get split-order status for a customer",
)
async def customer_status(customer_id: str):
    """Return all stored fragments and active alerts for a customer."""
    db = _conn()
    frags = db.execute(
        "SELECT id, order_id, length, ind_score, ind_decision, submitted_at, flagged "
        "FROM fragments WHERE customer_id=? ORDER BY submitted_at",
        (customer_id,),
    ).fetchall()
    alerts = db.execute(
        "SELECT id, assembly_score, fragment_ids, created_at "
        "FROM alerts WHERE customer_id=? ORDER BY created_at DESC",
        (customer_id,),
    ).fetchall()
    db.close()
    return CustomerStatus(
        customer_id=customer_id,
        fragment_count=len(frags),
        flagged_count=sum(1 for f in frags if f["flagged"]),
        alerts=[dict(a) for a in alerts],
        fragments=[dict(f) for f in frags],
    )


@router.delete(
    "/customer/{customer_id}/flush",
    summary="Flush all fragment state for a customer",
)
async def flush_customer(customer_id: str):
    """Remove all fragments and alerts for a customer (use after order resolution)."""
    db = _conn()
    db.execute("DELETE FROM fragments WHERE customer_id=?", (customer_id,))
    db.execute("DELETE FROM alerts WHERE customer_id=?", (customer_id,))
    db.commit()
    db.close()
    return {"ok": True, "customer_id": customer_id, "message": "All fragment state cleared."}
