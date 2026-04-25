"""
services/automation.py
───────────────────────
Rules-based automation engine for BioLens.

Supervisors can define AutoEscalation rules that automatically apply
analyst status overrides when a newly screened case matches active
watchlist items with sufficient severity.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from services.constants import AUTOMATION_ACTIONS, ANALYST_STATUSES
from services.storage import get_connection, utc_now_iso


# ── Schema migration ───────────────────────────────────────────────────────────

def init_automation_tables() -> None:
    """Create automation tables if they don't exist (called from storage.init_db)."""
    statements = (
        """
        CREATE TABLE IF NOT EXISTS automation_rules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            trigger_priority TEXT NOT NULL,
            trigger_severity TEXT NOT NULL,
            action TEXT NOT NULL,
            target_status TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL DEFAULT 'Supervisor',
            created_at TEXT NOT NULL,
            fire_count INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS automation_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id TEXT NOT NULL,
            rule_name TEXT NOT NULL,
            case_id TEXT NOT NULL,
            action_taken TEXT NOT NULL,
            match_reason TEXT NOT NULL,
            fired_at TEXT NOT NULL,
            FOREIGN KEY (case_id) REFERENCES screenings(id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_auto_log_case ON automation_log(case_id)",
        "CREATE INDEX IF NOT EXISTS idx_auto_log_rule ON automation_log(rule_id)",
    )
    with get_connection() as conn:
        for stmt in statements:
            conn.execute(stmt)
        conn.commit()


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class AutomationRule:
    id: str
    name: str
    description: str
    trigger_priority: str          # Watchlist match priority that triggers this rule: LOW | MEDIUM | HIGH
    trigger_severity: str          # Alert severity threshold: LOW | MEDIUM | HIGH
    action: str                    # From AUTOMATION_ACTIONS
    target_status: str             # Analyst status to set, e.g. ESCALATED
    enabled: bool
    created_by: str
    created_at: str
    fire_count: int = 0


def _row_to_rule(row: dict[str, Any]) -> AutomationRule:
    return AutomationRule(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        trigger_priority=row["trigger_priority"],
        trigger_severity=row["trigger_severity"],
        action=row["action"],
        target_status=row["target_status"],
        enabled=bool(row["enabled"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
        fire_count=row.get("fire_count", 0),
    )


# ── CRUD ───────────────────────────────────────────────────────────────────────

def list_rules(enabled_only: bool = False) -> list[AutomationRule]:
    init_automation_tables()
    query = "SELECT * FROM automation_rules"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY created_at DESC"
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
    return [_row_to_rule(dict(row)) for row in rows]


def create_rule(
    name: str,
    description: str,
    trigger_priority: str,
    trigger_severity: str,
    action: str,
    target_status: str,
    created_by: str = "Supervisor",
) -> AutomationRule:
    """Create a new automation rule. Returns the created rule."""
    init_automation_tables()

    if trigger_priority not in ("LOW", "MEDIUM", "HIGH"):
        raise ValueError(f"Invalid trigger_priority: {trigger_priority}")
    if trigger_severity not in ("LOW", "MEDIUM", "HIGH"):
        raise ValueError(f"Invalid trigger_severity: {trigger_severity}")
    if action not in AUTOMATION_ACTIONS:
        raise ValueError(f"Invalid action: {action}")
    if target_status not in ANALYST_STATUSES:
        raise ValueError(f"Invalid target_status: {target_status}")

    rule_id = str(uuid.uuid4())
    now = utc_now_iso()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO automation_rules
                (id, name, description, trigger_priority, trigger_severity,
                 action, target_status, enabled, created_by, created_at, fire_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 0)
            """,
            (rule_id, name, description, trigger_priority, trigger_severity,
             action, target_status, created_by, now),
        )
        conn.commit()

    return AutomationRule(
        id=rule_id, name=name, description=description,
        trigger_priority=trigger_priority, trigger_severity=trigger_severity,
        action=action, target_status=target_status, enabled=True,
        created_by=created_by, created_at=now,
    )


def toggle_rule(rule_id: str, enabled: bool) -> None:
    """Enable or disable a rule."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE automation_rules SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, rule_id),
        )
        conn.commit()


def delete_rule(rule_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM automation_rules WHERE id = ?", (rule_id,))
        conn.commit()


def get_automation_log(limit: int = 100) -> list[dict[str, Any]]:
    init_automation_tables()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM automation_log ORDER BY fired_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_case_automation_log(case_id: str) -> list[dict[str, Any]]:
    init_automation_tables()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM automation_log WHERE case_id = ? ORDER BY fired_at DESC",
            (case_id,),
        ).fetchall()
    return [dict(row) for row in rows]


# ── Rule evaluation engine ─────────────────────────────────────────────────────

_PRIORITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def evaluate_auto_rules(
    case_id: str,
    intel_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Evaluate active automation rules against a set of intelligence matches.

    Returns a list of fired rule results:
        [{rule_name, action, target_status, match_reason}]

    Also persists firings to automation_log and increments fire_count.
    """
    if not intel_matches:
        return []

    rules = list_rules(enabled_only=True)
    if not rules:
        return []

    fired: list[dict[str, Any]] = []

    for rule in rules:
        rule_priority_rank = _PRIORITY_RANK.get(rule.trigger_priority, 1)
        rule_severity_rank = _SEVERITY_RANK.get(rule.trigger_severity, 1)

        for match in intel_matches:
            match_priority_rank = _PRIORITY_RANK.get(match.get("priority", "LOW"), 1)
            match_severity_rank = _SEVERITY_RANK.get(match.get("severity", "LOW"), 1)

            if (match_priority_rank >= rule_priority_rank and
                    match_severity_rank >= rule_severity_rank):

                match_reason = (
                    f"Rule '{rule.name}': matched watchlist keyword "
                    f"'{match.get('keyword', '?')}' "
                    f"(Priority: {match.get('priority')}, Alert Severity: {match.get('severity')})"
                )

                # Log the firing
                now = utc_now_iso()
                with get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO automation_log
                            (rule_id, rule_name, case_id, action_taken, match_reason, fired_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (rule.id, rule.name, case_id, rule.action, match_reason, now),
                    )
                    conn.execute(
                        "UPDATE automation_rules SET fire_count = fire_count + 1 WHERE id = ?",
                        (rule.id,),
                    )
                    conn.commit()

                fired.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "action": rule.action,
                    "target_status": rule.target_status,
                    "match_reason": match_reason,
                })
                break  # One firing per rule per case

    return fired


def seed_default_rules() -> None:
    """Insert sensible default rules if none exist yet."""
    init_automation_tables()
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM automation_rules").fetchone()[0]
        if count > 0:
            return

    default_rules = [
        {
            "name": "Auto-Escalate HIGH Intel + HIGH Priority Match",
            "description": "Automatically escalate any case where a HIGH-severity alert matches at HIGH watchlist priority.",
            "trigger_priority": "HIGH",
            "trigger_severity": "HIGH",
            "action": "AUTO_ESCALATE",
            "target_status": "ESCALATED",
        },
        {
            "name": "Flag for Review on MEDIUM Alert Match",
            "description": "Set status to IN_REVIEW when a MEDIUM or higher severity alert matches.",
            "trigger_priority": "MEDIUM",
            "trigger_severity": "MEDIUM",
            "action": "FLAG_FOR_REVIEW",
            "target_status": "IN_REVIEW",
        },
    ]
    for r in default_rules:
        create_rule(**r)
