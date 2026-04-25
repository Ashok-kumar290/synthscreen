from __future__ import annotations

import os

from services.constants import RUNTIME_MODES, UI_MODES

# Map legacy mode values to the current two-mode system.
_LEGACY_MODE_MAP = {"integrated": "online", "demo": "offline", "mock": "offline"}


def get_runtime_mode() -> str:
    mode = os.getenv("BIOLENS_MODE", "offline").strip().lower()
    mode = _LEGACY_MODE_MAP.get(mode, mode)
    if mode not in RUNTIME_MODES:
        return "offline"
    return mode


def get_ui_mode() -> str:
    mode = os.getenv("BIOLENS_UI_MODE", "compact").strip().lower()
    return mode if mode in UI_MODES else "compact"



def bootstrap_application() -> None:
    from services.storage import init_db

    init_db()
