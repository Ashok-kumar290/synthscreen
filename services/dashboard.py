"""
services/dashboard.py
──────────────────────
Unified situational awareness computations for the BioLens home dashboard.
Provides threat posture scoring, unified activity feed, response time metrics,
and regional threat summaries.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.constants import THREAT_POSTURE_LEVELS
from services.intelligence import get_active_threat_regions, list_alerts
from services.storage import analytics_snapshot, get_connection


# ── Threat Posture ─────────────────────────────────────────────────────────────

def compute_threat_posture() -> dict[str, Any]:
    """
    Compute the overall operational threat posture from intelligence signals
    and screening queue state.

    Returns:
        {
            "level": "NORMAL" | "ELEVATED" | "HIGH",
            "score": 0–100,
            "drivers": [list of contributing factors],
        }
    """
    alerts = list_alerts()
    active_alerts = [a for a in alerts if a["status"] not in ("DISMISSED", "REVIEWED")]
    high_alerts = [a for a in active_alerts if a["severity"] == "HIGH"]
    medium_alerts = [a for a in active_alerts if a["severity"] == "MEDIUM"]

    snapshot = analytics_snapshot()
    open_queue = snapshot.get("open_queue", 0)
    flagged_rate = snapshot.get("flagged_rate", 0.0)

    # Weighted score (0–100)
    score = 0
    drivers: list[str] = []

    if high_alerts:
        score += min(len(high_alerts) * 20, 50)
        drivers.append(f"{len(high_alerts)} HIGH-severity intelligence alert(s) active")

    if medium_alerts:
        score += min(len(medium_alerts) * 8, 20)
        drivers.append(f"{len(medium_alerts)} MEDIUM-severity alert(s) active")

    if open_queue > 10:
        score += 20
        drivers.append(f"Open review queue depth: {open_queue} cases")
    elif open_queue > 5:
        score += 10
        drivers.append(f"Elevated review queue: {open_queue} cases pending")

    if flagged_rate > 0.4:
        score += 15
        drivers.append(f"High flagged rate: {flagged_rate:.0%} of screened sequences flagged")
    elif flagged_rate > 0.2:
        score += 7
        drivers.append(f"Elevated flagged rate: {flagged_rate:.0%}")

    score = min(score, 100)

    if score >= 50:
        level = "HIGH"
    elif score >= 20:
        level = "ELEVATED"
    else:
        level = "NORMAL"

    if not drivers:
        drivers.append("No elevated threat signals detected")

    return {
        "level": level,
        "score": score,
        "drivers": drivers,
        "active_alert_count": len(active_alerts),
        "high_alert_count": len(high_alerts),
    }


# ── Unified Activity Feed ──────────────────────────────────────────────────────

def get_unified_activity_feed(limit: int = 20) -> list[dict[str, Any]]:
    """
    Merge recent screening events and intelligence alerts into a single
    time-ordered activity feed.

    Each item has:
        type: "screening" | "alert"
        timestamp: ISO string
        title: human-readable summary
        severity / risk_level: for colour coding
        link_id: id to navigate to the relevant page
        meta: additional display fields
    """
    items: list[dict[str, Any]] = []

    # Recent screenings
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, submitted_at, risk_level, hazard_score, category,
                   analyst_status, sequence_type, data_source
            FROM screenings
            ORDER BY submitted_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    for row in rows:
        row_dict = dict(row)
        items.append({
            "type": "screening",
            "timestamp": row_dict["submitted_at"],
            "title": f"Sequence screened — {row_dict['category']}",
            "risk_level": row_dict["risk_level"],
            "severity": None,
            "link_id": row_dict["id"],
            "meta": {
                "hazard_score": row_dict["hazard_score"],
                "analyst_status": row_dict["analyst_status"],
                "sequence_type": row_dict["sequence_type"],
                "data_source": row_dict.get("data_source", "unknown"),
            },
        })

    # Recent intelligence alerts
    alerts = list_alerts()
    for alert in alerts[:limit]:
        items.append({
            "type": "alert",
            "timestamp": alert["created_at"],
            "title": alert["title"],
            "risk_level": None,
            "severity": alert["severity"],
            "link_id": alert["id"],
            "meta": {
                "source_name": alert["source_name"],
                "signal_type": alert["signal_type"],
                "region": alert["region"],
                "status": alert["status"],
            },
        })

    # Sort by timestamp descending and take the top `limit` items
    items.sort(key=lambda x: x["timestamp"] or "", reverse=True)
    return items[:limit]


# ── Response Time Metrics ──────────────────────────────────────────────────────

def get_response_time_metrics() -> dict[str, Any]:
    """
    Compute how fast cases move through the pipeline (submitted → reviewed).
    Returns mean/median/p90 response times in hours, broken down by risk tier.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT risk_level, submitted_at, reviewed_at
            FROM screenings
            WHERE reviewed_at IS NOT NULL AND submitted_at IS NOT NULL
            ORDER BY reviewed_at DESC
            LIMIT 500
            """
        ).fetchall()

    if not rows:
        return {"overall": None, "by_risk": {}, "sample_count": 0}

    def _parse(ts: str) -> datetime | None:
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None

    deltas_by_risk: dict[str, list[float]] = {}
    all_deltas: list[float] = []

    for row in rows:
        submitted = _parse(row["submitted_at"])
        reviewed = _parse(row["reviewed_at"])
        if not submitted or not reviewed:
            continue
        hours = (reviewed - submitted).total_seconds() / 3600
        if hours < 0:
            continue
        all_deltas.append(hours)
        risk = row["risk_level"]
        deltas_by_risk.setdefault(risk, []).append(hours)

    def _stats(vals: list[float]) -> dict[str, float]:
        if not vals:
            return {}
        s = sorted(vals)
        n = len(s)
        return {
            "mean_hours": round(sum(s) / n, 2),
            "median_hours": round(s[n // 2], 2),
            "p90_hours": round(s[int(n * 0.9)], 2),
            "count": n,
        }

    return {
        "overall": _stats(all_deltas),
        "by_risk": {risk: _stats(vals) for risk, vals in deltas_by_risk.items()},
        "sample_count": len(all_deltas),
    }


# ── Regional Threat Summary ────────────────────────────────────────────────────

def get_regional_threat_summary() -> list[dict[str, Any]]:
    """
    Aggregate active alerts by region with severity weighting, for the heatmap.
    Returns list sorted by threat score descending.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                region,
                COUNT(*) AS total_alerts,
                SUM(CASE WHEN severity = 'HIGH' THEN 3 WHEN severity = 'MEDIUM' THEN 2 ELSE 1 END) AS threat_score,
                SUM(CASE WHEN severity = 'HIGH' THEN 1 ELSE 0 END) AS high_count,
                SUM(CASE WHEN severity = 'MEDIUM' THEN 1 ELSE 0 END) AS medium_count,
                SUM(CASE WHEN severity = 'LOW' THEN 1 ELSE 0 END) AS low_count,
                GROUP_CONCAT(DISTINCT signal_type) AS signal_types
            FROM intelligence_alerts
            WHERE status NOT IN ('DISMISSED')
            GROUP BY region
            ORDER BY threat_score DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]
