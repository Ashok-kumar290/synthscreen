from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from services.constants import ALERT_SEVERITIES, ALERT_SIGNAL_TYPES, ALERT_SOURCE_TYPES, ALERT_STATUSES, DATA_DIR
from services.storage import get_connection, init_db, utc_now_iso


# ── Demo data loading ──────────────────────────────────────────────────────────

def load_demo_alerts() -> list[dict[str, Any]]:
    path = DATA_DIR / "demo_intelligence.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_demo_alerts() -> None:
    init_db()
    with get_connection() as connection:
        count = connection.execute("SELECT COUNT(*) FROM intelligence_alerts").fetchone()[0]
        if count > 0:
            return

    demo_alerts = load_demo_alerts()
    for alert in demo_alerts:
        insert_alert({
            "id": alert["id"],
            "title": alert["title"],
            "summary": alert["summary"],
            "source_type": alert["source_type"],
            "source_name": alert["source_name"],
            "region": alert["region"],
            "signal_type": alert["signal_type"],
            "severity": alert["severity"],
            "confidence": alert["confidence"],
            "screening_relevance": alert["screening_relevance"],
            "suggested_action": alert["suggested_action"],
            "status": alert.get("status", "NEW"),
        })


# ── Core CRUD ──────────────────────────────────────────────────────────────────

def insert_alert(alert: dict[str, Any]) -> None:
    columns = (
        "id", "title", "summary", "source_type", "source_name", "region",
        "signal_type", "severity", "confidence", "screening_relevance",
        "suggested_action", "created_at", "status"
    )
    values = (
        alert.get("id") or str(uuid.uuid4()),
        alert["title"],
        alert["summary"],
        alert["source_type"],
        alert["source_name"],
        alert["region"],
        alert["signal_type"],
        alert["severity"],
        float(alert["confidence"]),
        alert["screening_relevance"],
        alert["suggested_action"],
        alert.get("created_at") or utc_now_iso(),
        alert.get("status", "NEW")
    )
    with get_connection() as connection:
        connection.execute(
            f"INSERT OR IGNORE INTO intelligence_alerts ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            values
        )
        connection.commit()


def create_manual_alert(
    title: str,
    summary: str,
    source_type: str,
    source_name: str,
    region: str,
    signal_type: str,
    severity: str,
    confidence: float,
    screening_relevance: str,
    suggested_action: str,
) -> str:
    """Create a new intelligence alert authored by an operator. Returns the new alert ID."""
    if source_type not in ALERT_SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {source_type}")
    if signal_type not in ALERT_SIGNAL_TYPES:
        raise ValueError(f"Invalid signal_type: {signal_type}")
    if severity not in ALERT_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity}")

    alert_id = str(uuid.uuid4())
    insert_alert({
        "id": alert_id,
        "title": title.strip(),
        "summary": summary.strip(),
        "source_type": source_type,
        "source_name": source_name.strip(),
        "region": region.strip(),
        "signal_type": signal_type,
        "severity": severity,
        "confidence": float(confidence),
        "screening_relevance": screening_relevance.strip(),
        "suggested_action": suggested_action.strip(),
        "status": "NEW",
    })
    return alert_id


def import_alerts_from_json(raw_json: str) -> dict[str, int]:
    """Bulk-import alerts from a JSON string (list of alert dicts). Returns insert stats."""
    try:
        records = json.loads(raw_json)
        if not isinstance(records, list):
            raise ValueError("Expected a JSON array of alert objects.")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    inserted = 0
    skipped = 0
    for rec in records:
        try:
            # Normalise – required fields only, fill optional ones
            insert_alert({
                "id": rec.get("id") or str(uuid.uuid4()),
                "title": rec["title"],
                "summary": rec.get("summary", ""),
                "source_type": rec.get("source_type", "MOCK"),
                "source_name": rec.get("source_name", "Imported"),
                "region": rec.get("region", "Global"),
                "signal_type": rec.get("signal_type", "RESEARCH_SIGNAL"),
                "severity": rec.get("severity", "LOW"),
                "confidence": float(rec.get("confidence", 50)),
                "screening_relevance": rec.get("screening_relevance", ""),
                "suggested_action": rec.get("suggested_action", "Review."),
                "status": rec.get("status", "NEW"),
                "created_at": rec.get("created_at"),
            })
            inserted += 1
        except (KeyError, TypeError, ValueError):
            skipped += 1
    return {"inserted": inserted, "skipped": skipped, "total": inserted + skipped}


def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    signal_type: str | None = None,
    region: str | None = None
) -> list[dict[str, Any]]:
    query = "SELECT * FROM intelligence_alerts"
    where = []
    params = []
    if status:
        where.append("status = ?")
        params.append(status)
    if severity:
        where.append("severity = ?")
        params.append(severity)
    if signal_type:
        where.append("signal_type = ?")
        params.append(signal_type)
    if region and region != "All Regions":
        where.append("region = ?")
        params.append(region)

    if where:
        query += " WHERE " + " AND ".join(where)

    query += " ORDER BY created_at DESC"

    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_alert(alert_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM intelligence_alerts WHERE id = ?", (alert_id,)).fetchone()
    return dict(row) if row else None


def update_alert_status(alert_id: str, new_status: str) -> None:
    if new_status not in ALERT_STATUSES:
        raise ValueError(f"Invalid alert status: {new_status}")
    with get_connection() as connection:
        connection.execute("UPDATE intelligence_alerts SET status = ? WHERE id = ?", (new_status, alert_id))
        connection.commit()


def update_alert_fields(alert_id: str, **fields: Any) -> None:
    """Update arbitrary editable fields of an existing alert (title, summary, suggested_action, etc.)."""
    allowed = {"title", "summary", "source_name", "region", "screening_relevance", "suggested_action", "confidence", "severity"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    assignments = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [alert_id]
    with get_connection() as connection:
        connection.execute(f"UPDATE intelligence_alerts SET {assignments} WHERE id = ?", params)
        connection.commit()


# ── Timeline & statistics ──────────────────────────────────────────────────────

def get_alert_timeline() -> list[dict[str, Any]]:
    """Return alerts grouped by date for timeline visualisation (date, count, high_count, regions)."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                substr(created_at, 1, 10) AS day,
                COUNT(*) AS count,
                SUM(CASE WHEN severity = 'HIGH' THEN 1 ELSE 0 END) AS high_count,
                GROUP_CONCAT(DISTINCT region) AS regions
            FROM intelligence_alerts
            GROUP BY substr(created_at, 1, 10)
            ORDER BY day ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_alert_statistics() -> dict[str, Any]:
    """Return aggregate counts for the intelligence analytics panel."""
    with get_connection() as connection:
        total = connection.execute("SELECT COUNT(*) FROM intelligence_alerts").fetchone()[0]
        by_severity = [dict(r) for r in connection.execute(
            "SELECT severity, COUNT(*) AS count FROM intelligence_alerts GROUP BY severity"
        ).fetchall()]
        by_signal_type = [dict(r) for r in connection.execute(
            "SELECT signal_type, COUNT(*) AS count FROM intelligence_alerts GROUP BY signal_type ORDER BY count DESC"
        ).fetchall()]
        by_region = [dict(r) for r in connection.execute(
            "SELECT region, COUNT(*) AS count, MAX(severity) AS max_severity FROM intelligence_alerts GROUP BY region ORDER BY count DESC"
        ).fetchall()]
        by_status = [dict(r) for r in connection.execute(
            "SELECT status, COUNT(*) AS count FROM intelligence_alerts GROUP BY status"
        ).fetchall()]
        watchlist_count = connection.execute("SELECT COUNT(*) FROM watchlist_items WHERE active = 1").fetchone()[0]
        link_count = connection.execute("SELECT COUNT(*) FROM case_intelligence_links").fetchone()[0]

    return {
        "total": int(total),
        "by_severity": by_severity,
        "by_signal_type": by_signal_type,
        "by_region": by_region,
        "by_status": by_status,
        "active_watchlist_count": int(watchlist_count),
        "total_case_links": int(link_count),
    }


def get_watchlist_effectiveness() -> list[dict[str, Any]]:
    """For each active watchlist item, return how many cases it matched and their dispositions."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                w.id, w.keyword, w.category, w.region, w.priority,
                COUNT(l.id) AS match_count,
                SUM(CASE WHEN s.final_action = 'APPROVE' THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN s.final_action = 'HOLD' THEN 1 ELSE 0 END) AS held,
                SUM(CASE WHEN s.analyst_status = 'ESCALATED' THEN 1 ELSE 0 END) AS escalated
            FROM watchlist_items w
            LEFT JOIN case_intelligence_links l ON l.watchlist_id = w.id
            LEFT JOIN screenings s ON l.case_id = s.id
            WHERE w.active = 1
            GROUP BY w.id
            ORDER BY match_count DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


# ── Watchlist CRUD ─────────────────────────────────────────────────────────────

def score_alert(severity: str, confidence: float) -> str:
    severity_weight = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(severity, 1)
    if severity_weight >= 3 and confidence > 70:
        return "HIGH"
    if severity_weight >= 2 or confidence > 50:
        return "MEDIUM"
    return "LOW"


def add_to_watchlist(alert_id: str, keyword: str, category: str, region: str) -> None:
    alert = get_alert(alert_id)
    if not alert:
        return

    priority = score_alert(alert["severity"], alert["confidence"])
    reason = f"Added from alert: {alert['title'][:60]}"

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO watchlist_items (id, alert_id, keyword, category, region, priority, reason, created_at, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (str(uuid.uuid4()), alert_id, keyword, category, region, priority, reason, utc_now_iso())
        )
        connection.commit()

    update_alert_status(alert_id, "WATCHLISTED")


def remove_from_watchlist(watchlist_id: str) -> None:
    with get_connection() as connection:
        connection.execute("UPDATE watchlist_items SET active = 0 WHERE id = ?", (watchlist_id,))
        connection.commit()


def list_watchlist(active_only: bool = True) -> list[dict[str, Any]]:
    query = "SELECT * FROM watchlist_items"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY created_at DESC"

    with get_connection() as connection:
        rows = connection.execute(query).fetchall()
    return [dict(row) for row in rows]


# ── Intelligence ↔ Screening fusion ───────────────────────────────────────────

# Taxonomy expansion: synonyms map for richer keyword matching
_TAXONOMY_SYNONYMS: dict[str, list[str]] = {
    "hemorrhagic": ["filovirus", "arenavirus", "ebola", "marburg", "lassa", "hemorrhage"],
    "respiratory": ["influenza", "coronavirus", "sars", "mers", "rsv", "respiratory"],
    "viral vector": ["lentivirus", "adenovirus", "aav", "retrovirus", "vector"],
    "evasion": ["immune evasion", "codon substitution", "synonymous", "bypass"],
    "toxin": ["toxin", "ricin", "botulinum", "anthrax", "lethal factor"],
    "pathogen": ["pathogen", "virulence", "infection", "bacteria", "virus"],
}


def _expand_keywords(keyword: str) -> list[str]:
    """Return a list of semantically related terms for a given keyword."""
    kw_lower = keyword.lower()
    expanded = [kw_lower]
    for root, synonyms in _TAXONOMY_SYNONYMS.items():
        if kw_lower in synonyms or kw_lower == root:
            expanded.extend(synonyms)
            expanded.append(root)
    return list(set(expanded))


def match_case_to_watchlist(case_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Match a screening result against the active watchlist.
    Enhanced with taxonomy synonym expansion and severity-weighted scoring.
    """
    active_watchlist = list_watchlist(active_only=True)
    if not active_watchlist:
        return []

    text_to_search = (
        (case_metadata.get("category") or "") + " " +
        (case_metadata.get("explanation") or "") + " " +
        (case_metadata.get("sequence_type") or "")
    ).lower()

    matches = []
    for item in active_watchlist:
        kw = item["keyword"].lower()
        cat = item["category"].lower()
        expanded = _expand_keywords(kw)

        hit = any(term in text_to_search for term in expanded)
        if not hit:
            continue

        alert = get_alert(item["alert_id"])
        if not alert:
            continue

        matches.append({
            "watchlist_id": item["id"],
            "alert_id": alert["id"],
            "alert_title": alert["title"],
            "keyword": item["keyword"],
            "category": item["category"],
            "priority": item["priority"],
            "region": alert["region"],
            "severity": alert["severity"],
            "confidence": alert["confidence"],
            "screening_relevance": alert["screening_relevance"],
            "suggested_action": alert["suggested_action"],
            "match_reason": f"Matched watchlist keyword '{item['keyword']}' (expanded: {', '.join(expanded[:3])})",
        })

    # Deduplicate by alert_id, keeping highest-priority match
    seen: dict[str, dict[str, Any]] = {}
    priority_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    for m in matches:
        aid = m["alert_id"]
        if aid not in seen or priority_order.get(m["priority"], 0) > priority_order.get(seen[aid]["priority"], 0):
            seen[aid] = m

    return list(seen.values())


def compute_intelligence_risk_modifier(matches: list[dict[str, Any]]) -> float:
    """
    Compute a risk modifier (0.0–0.25) based on matched watchlist items.
    HIGH priority match = +0.15, MEDIUM = +0.08, LOW = +0.03.
    Capped at 0.25 total.
    """
    if not matches:
        return 0.0
    priority_weights = {"HIGH": 0.15, "MEDIUM": 0.08, "LOW": 0.03}
    total = sum(priority_weights.get(m["priority"], 0.03) for m in matches)
    return round(min(total, 0.25), 3)


def get_active_threat_regions() -> list[dict[str, Any]]:
    """Return regions that have HIGH severity active alerts."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT region, COUNT(*) AS alert_count, MAX(confidence) AS max_confidence
            FROM intelligence_alerts
            WHERE severity = 'HIGH' AND status NOT IN ('DISMISSED', 'REVIEWED')
            GROUP BY region
            ORDER BY alert_count DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_active_threat_keywords() -> list[str]:
    """Return all active watchlist keywords for screening-time display."""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT DISTINCT keyword FROM watchlist_items WHERE active = 1 ORDER BY keyword"
        ).fetchall()
    return [row["keyword"] for row in rows]


# ── Case ↔ Alert linking ───────────────────────────────────────────────────────

def link_case_to_alert(case_id: str, alert_id: str, watchlist_id: str, match_reason: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO case_intelligence_links (id, case_id, alert_id, watchlist_id, match_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), case_id, alert_id, watchlist_id, match_reason, utc_now_iso())
        )
        connection.commit()


def get_case_intelligence(case_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT l.match_reason, l.created_at, w.keyword, w.category as w_category, w.priority,
                   a.id as alert_id, a.title, a.region, a.severity, a.confidence,
                   a.screening_relevance, a.suggested_action
            FROM case_intelligence_links l
            LEFT JOIN watchlist_items w ON l.watchlist_id = w.id
            LEFT JOIN intelligence_alerts a ON l.alert_id = a.id
            WHERE l.case_id = ?
            ORDER BY l.created_at DESC
            """,
            (case_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_cases_with_intelligence_links(case_ids: list[str]) -> set[str]:
    """
    Return a set of case IDs (from the provided list) that have at least one
    intelligence link. Uses a single IN() query instead of per-case lookups,
    eliminating the O(N) DB call pattern in the Inbox page.
    """
    if not case_ids:
        return set()
    placeholders = ", ".join("?" for _ in case_ids)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT DISTINCT case_id FROM case_intelligence_links WHERE case_id IN ({placeholders})",
            case_ids,
        ).fetchall()
    return {row["case_id"] for row in rows}
