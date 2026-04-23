from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Sequence

from services.storage import fetch_screenings_with_audit


EXPORT_FIELDS = (
    "id",
    "submitted_at",
    "sequence_type",
    "sequence_text",
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
)


def build_export_dataset(screening_ids: Sequence[str] | None = None) -> list[dict]:
    records = fetch_screenings_with_audit(screening_ids)
    exported: list[dict] = []
    for record in records:
        item = {field: record.get(field) for field in EXPORT_FIELDS}
        item["audit_log"] = record.get("audit_log", [])
        exported.append(item)
    return exported


def export_screenings_csv(records: list[dict]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[*EXPORT_FIELDS, "audit_log"])
    writer.writeheader()
    for record in records:
        row = {field: record.get(field) for field in EXPORT_FIELDS}
        row["audit_log"] = json.dumps(record.get("audit_log", []), ensure_ascii=True)
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def export_screenings_json(records: list[dict]) -> bytes:
    return json.dumps(records, indent=2).encode("utf-8")


def export_filename(prefix: str, extension: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{timestamp}.{extension}"
