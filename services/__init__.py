from __future__ import annotations

import os

from services.constants import RUNTIME_MODES


def get_runtime_mode() -> str:
    mode = os.getenv("BIOLENS_MODE", "mock").strip().lower()
    if mode not in RUNTIME_MODES:
        return "mock"
    return mode


def bootstrap_application() -> None:
    from services.seed_data import ensure_demo_cases
    from services.storage import init_db

    init_db()
    if get_runtime_mode() == "demo":
        ensure_demo_cases()
