from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from services.constants import ANALYST_STATUSES, DEFAULT_DB_PATH, FINAL_ACTIONS, RISK_LEVELS


SCREENING_COLUMNS = (
    "id",
    "submitted_at",
    "sequence_text",
    "sequence_type",
    "hazard_score",
    "risk_level",
    "confidence",
    "category",
    "explanation",
    "baseline_result",
    "model_name",
    "analyst_status",
    "analyst_notes",
    "final_action",
    "reviewed_at",
    "threat_breakdown",
    "attribution_data",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_db_path() -> Path:
    raw_path = os.getenv("BIOLENS_DB_PATH", str(DEFAULT_DB_PATH))
    path = Path(raw_path)
    if not path.is_absolute():
        path = DEFAULT_DB_PATH.parent.parent / raw_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(get_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    statements = (
        """
        CREATE TABLE IF NOT EXISTS screenings (
            id TEXT PRIMARY KEY,
            submitted_at TEXT NOT NULL,
            sequence_text TEXT NOT NULL,
            sequence_type TEXT NOT NULL,
            hazard_score REAL NOT NULL,
            risk_level TEXT NOT NULL,
            confidence REAL NOT NULL,
            category TEXT NOT NULL,
            explanation TEXT NOT NULL,
            baseline_result TEXT,
            model_name TEXT NOT NULL,
            analyst_status TEXT NOT NULL DEFAULT 'NEW',
            analyst_notes TEXT,
            final_action TEXT,
            reviewed_at TEXT,
            threat_breakdown TEXT,
            attribution_data TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            screening_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            details TEXT NOT NULL,
            FOREIGN KEY (screening_id) REFERENCES screenings(id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_screenings_submitted_at ON screenings(submitted_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_screenings_status ON screenings(analyst_status)",
        "CREATE INDEX IF NOT EXISTS idx_screenings_risk ON screenings(risk_level)",
        "CREATE INDEX IF NOT EXISTS idx_audit_screening_id ON audit_log(screening_id, event_time)",
    )

    with get_connection() as connection:
        for statement in statements:
            connection.execute(statement)
        connection.commit()


def _normalize_screening_record(record: dict[str, Any]) -> dict[str, Any]:
    risk_level = str(record["risk_level"])
    if risk_level not in RISK_LEVELS:
        raise ValueError(f"Invalid risk level: {risk_level}")

    sequence_type = str(record["sequence_type"])
    if sequence_type not in {"DNA", "PROTEIN"}:
        raise ValueError(f"Invalid sequence type: {sequence_type}")

    analyst_status = str(record.get("analyst_status") or "NEW")
    if analyst_status not in ANALYST_STATUSES:
        raise ValueError(f"Invalid analyst status: {analyst_status}")

    final_action = record.get("final_action")
    if final_action is not None and final_action not in FINAL_ACTIONS:
        raise ValueError(f"Invalid final action: {final_action}")

    return {
        "id": str(record.get("id") or uuid.uuid4()),
        "submitted_at": str(record.get("submitted_at") or utc_now_iso()),
        "sequence_text": str(record["sequence_text"]).strip(),
        "sequence_type": sequence_type,
        "hazard_score": float(record["hazard_score"]),
        "risk_level": risk_level,
        "confidence": float(record["confidence"]),
        "category": str(record["category"]),
        "explanation": str(record["explanation"]),
        "baseline_result": record.get("baseline_result"),
        "model_name": str(record["model_name"]),
        "analyst_status": analyst_status,
        "analyst_notes": (str(record.get("analyst_notes")).strip() or None) if record.get("analyst_notes") is not None else None,
        "final_action": final_action,
        "reviewed_at": record.get("reviewed_at"),
        "threat_breakdown": json.dumps(record.get("threat_breakdown")) if record.get("threat_breakdown") else None,
        "attribution_data": json.dumps(record.get("attribution_data")) if record.get("attribution_data") else None,
    }


def insert_screening_record(
    record: dict[str, Any],
    audit_events: Sequence[dict[str, Any]] | None = None,
    ignore_existing: bool = False,
) -> tuple[str, bool]:
    init_db()
    normalized = _normalize_screening_record(record)
    placeholder = " OR IGNORE" if ignore_existing else ""
    column_sql = ", ".join(SCREENING_COLUMNS)
    parameter_sql = ", ".join("?" for _ in SCREENING_COLUMNS)
    values = [normalized[column] for column in SCREENING_COLUMNS]

    with get_connection() as connection:
        cursor = connection.execute(
            f"INSERT{placeholder} INTO screenings ({column_sql}) VALUES ({parameter_sql})",
            values,
        )
        inserted = cursor.rowcount > 0
        if inserted:
            for event in audit_events or []:
                connection.execute(
                    "INSERT INTO audit_log (screening_id, event_type, event_time, details) VALUES (?, ?, ?, ?)",
                    (
                        normalized["id"],
                        event["event_type"],
                        event.get("event_time") or utc_now_iso(),
                        json.dumps(event.get("details") or {}, ensure_ascii=True, sort_keys=True),
                    ),
                )
        connection.commit()
    return normalized["id"], inserted


def save_screening_case(sequence_text: str, sequence_type: str, result: dict[str, Any]) -> str:
    if not result.get("ok"):
        raise ValueError("Only successful screening results can be saved.")

    screening_id, _ = insert_screening_record(
        {
            "sequence_text": sequence_text,
            "sequence_type": sequence_type,
            "hazard_score": result["hazard_score"],
            "risk_level": result["risk_level"],
            "confidence": result["confidence"],
            "category": result["category"],
            "explanation": result["explanation"],
            "baseline_result": result["baseline_result"],
            "model_name": result["model_name"],
            "analyst_status": "NEW",
            "analyst_notes": None,
            "final_action": None,
            "reviewed_at": None,
            "threat_breakdown": result.get("threat_breakdown"),
            "attribution_data": result.get("attribution_data"),
        },
        audit_events=[
            {
                "event_type": "case_created",
                "details": {
                    "risk_level": result["risk_level"],
                    "hazard_score": result["hazard_score"],
                    "model_name": result["model_name"],
                },
            }
        ],
    )
    return screening_id


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def get_screening(screening_id: str) -> dict[str, Any]:
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM screenings WHERE id = ?", (screening_id,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown screening id: {screening_id}")
    
    result_dict = dict(row)
    if result_dict.get("threat_breakdown"):
        result_dict["threat_breakdown"] = json.loads(result_dict["threat_breakdown"])
    if result_dict.get("attribution_data"):
        result_dict["attribution_data"] = json.loads(result_dict["attribution_data"])
        
    return result_dict


def list_screenings(
    statuses: Sequence[str] | None = None,
    risk_levels: Sequence[str] | None = None,
    sort_by: str = "submitted_at",
    descending: bool = True,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    allowed_sort_columns = {
        "submitted_at": "submitted_at",
        "hazard_score": "hazard_score",
        "confidence": "confidence",
        "reviewed_at": "reviewed_at",
    }
    where_parts: list[str] = []
    params: list[Any] = []

    if statuses:
        where_parts.append(f"analyst_status IN ({', '.join('?' for _ in statuses)})")
        params.extend(statuses)
    if risk_levels:
        where_parts.append(f"risk_level IN ({', '.join('?' for _ in risk_levels)})")
        params.extend(risk_levels)

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    direction = "DESC" if descending else "ASC"
    sort_column = allowed_sort_columns.get(sort_by, "submitted_at")
    limit_clause = "LIMIT ?" if limit is not None else ""
    if limit is not None:
        params.append(limit)

    query = (
        f"SELECT * FROM screenings {where_clause} "
        f"ORDER BY {sort_column} {direction}, submitted_at DESC {limit_clause}"
    )
    with get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def list_audit_events(screening_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM audit_log WHERE screening_id = ? ORDER BY event_time ASC, id ASC",
            (screening_id,),
        ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["details"] = json.loads(event["details"])
        events.append(event)
    return events


def update_review(
    screening_id: str,
    analyst_status: str,
    analyst_notes: str | None,
    final_action: str | None,
) -> dict[str, Any]:
    if analyst_status not in ANALYST_STATUSES:
        raise ValueError(f"Invalid analyst status: {analyst_status}")
    if final_action is not None and final_action not in FINAL_ACTIONS:
        raise ValueError(f"Invalid final action: {final_action}")

    existing = get_screening(screening_id)
    cleaned_notes = analyst_notes.strip() if analyst_notes else None
    updates: dict[str, Any] = {}
    audit_events: list[dict[str, Any]] = []

    if analyst_status != existing["analyst_status"]:
        updates["analyst_status"] = analyst_status
        audit_events.append(
            {
                "event_type": "status_change",
                "details": {"from": existing["analyst_status"], "to": analyst_status},
            }
        )
    if cleaned_notes != existing["analyst_notes"]:
        updates["analyst_notes"] = cleaned_notes
        audit_events.append(
            {
                "event_type": "notes_updated",
                "details": {"has_notes": bool(cleaned_notes), "length": len(cleaned_notes or "")},
            }
        )
    if final_action != existing["final_action"]:
        updates["final_action"] = final_action
        audit_events.append(
            {
                "event_type": "action_set",
                "details": {"from": existing["final_action"], "to": final_action},
            }
        )

    if not updates:
        return existing

    updates["reviewed_at"] = utc_now_iso()
    assignments = ", ".join(f"{column} = ?" for column in updates)
    parameters = list(updates.values()) + [screening_id]

    with get_connection() as connection:
        connection.execute(f"UPDATE screenings SET {assignments} WHERE id = ?", parameters)
        for event in audit_events:
            connection.execute(
                "INSERT INTO audit_log (screening_id, event_type, event_time, details) VALUES (?, ?, ?, ?)",
                (
                    screening_id,
                    event["event_type"],
                    utc_now_iso(),
                    json.dumps(event["details"], ensure_ascii=True, sort_keys=True),
                ),
            )
        connection.commit()

    return get_screening(screening_id)


def count_screenings() -> int:
    with get_connection() as connection:
        total = connection.execute("SELECT COUNT(*) FROM screenings").fetchone()[0]
    return int(total)


def fetch_screenings_with_audit(screening_ids: Sequence[str] | None = None) -> list[dict[str, Any]]:
    if screening_ids is not None:
        if not screening_ids:
            return []
        cases = [get_screening(screening_id) for screening_id in screening_ids]
    else:
        cases = list_screenings()

    for case in cases:
        case["audit_log"] = list_audit_events(case["id"])
    return cases


def analytics_snapshot() -> dict[str, Any]:
    with get_connection() as connection:
        total = int(connection.execute("SELECT COUNT(*) FROM screenings").fetchone()[0])
        flagged = int(
            connection.execute(
                "SELECT COUNT(*) FROM screenings WHERE risk_level IN ('REVIEW', 'HIGH')"
            ).fetchone()[0]
        )
        open_queue = int(
            connection.execute(
                "SELECT COUNT(*) FROM screenings WHERE analyst_status IN ('NEW', 'IN_REVIEW', 'ESCALATED')"
            ).fetchone()[0]
        )
        average_hazard = float(connection.execute("SELECT COALESCE(AVG(hazard_score), 0.0) FROM screenings").fetchone()[0])
        risk_distribution = [
            dict(row)
            for row in connection.execute(
                "SELECT risk_level, COUNT(*) AS count FROM screenings GROUP BY risk_level ORDER BY COUNT(*) DESC"
            ).fetchall()
        ]
        status_distribution = [
            dict(row)
            for row in connection.execute(
                "SELECT analyst_status, COUNT(*) AS count FROM screenings GROUP BY analyst_status ORDER BY COUNT(*) DESC"
            ).fetchall()
        ]
        top_categories = [
            dict(row)
            for row in connection.execute(
                """
                SELECT category, COUNT(*) AS count
                FROM screenings
                WHERE risk_level IN ('REVIEW', 'HIGH')
                GROUP BY category
                ORDER BY COUNT(*) DESC, category ASC
                LIMIT 5
                """
            ).fetchall()
        ]
        activity_over_time = [
            dict(row)
            for row in connection.execute(
                """
                SELECT substr(submitted_at, 1, 10) AS day, COUNT(*) AS count
                FROM screenings
                GROUP BY substr(submitted_at, 1, 10)
                ORDER BY day ASC
                """
            ).fetchall()
        ]
        recent_flagged = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, risk_level, hazard_score, analyst_status, category, submitted_at
                FROM screenings
                WHERE risk_level IN ('REVIEW', 'HIGH')
                ORDER BY submitted_at DESC
                LIMIT 8
                """
            ).fetchall()
        ]

    flagged_rate = (flagged / total) if total else 0.0
    return {
        "total": total,
        "flagged": flagged,
        "flagged_rate": flagged_rate,
        "open_queue": open_queue,
        "average_hazard_score": average_hazard,
        "risk_distribution": risk_distribution,
        "status_distribution": status_distribution,
        "top_categories": top_categories,
        "activity_over_time": activity_over_time,
        "recent_flagged": recent_flagged,
    }
