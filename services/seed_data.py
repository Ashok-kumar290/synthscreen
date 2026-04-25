from __future__ import annotations

import json

from services.constants import DATA_DIR
from services.storage import count_screenings, insert_screening_record


DEMO_CASES_PATH = DATA_DIR / "demo_cases.json"
SAMPLE_DATASET_PATH = DATA_DIR / "sample_dataset.json"


def load_demo_cases() -> list[dict]:
    with DEMO_CASES_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_demo_cases() -> dict[str, int]:
    cases = load_demo_cases()
    inserted = 0

    for case in cases:
        screening = {key: case.get(key) for key in case.keys() if key != "audit_events"}
        _, created = insert_screening_record(
            screening,
            audit_events=case.get("audit_events", []),
            ignore_existing=True,
        )
        if created:
            inserted += 1

    return {"requested": len(cases), "inserted": inserted, "total": count_screenings()}


def load_sample_dataset() -> dict[str, int]:
    """Load the curated sample dataset for demo purposes."""
    if not SAMPLE_DATASET_PATH.exists():
        return {"requested": 0, "inserted": 0, "total": count_screenings()}
        
    cases = json.loads(SAMPLE_DATASET_PATH.read_text(encoding="utf-8"))
    inserted = 0
    for case in cases:
        screening = {k: v for k, v in case.items() if k != "audit_events"}
        _, created = insert_screening_record(
            screening, audit_events=case.get("audit_events", []), ignore_existing=True
        )
        if created:
            inserted += 1
    return {"requested": len(cases), "inserted": inserted, "total": count_screenings()}
