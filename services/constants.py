from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "biolens.db"

RUNTIME_MODES = ("offline", "demo", "integrated")
RISK_LEVELS = ("SAFE", "REVIEW", "HIGH")
ANALYST_STATUSES = ("NEW", "IN_REVIEW", "ESCALATED", "CLEARED", "CLOSED")
FINAL_ACTIONS = ("APPROVE", "MANUAL_REVIEW", "ESCALATE", "HOLD")

RISK_STYLES = {
    "SAFE": {"bg": "#e6f5ee", "fg": "#1f6a4d"},
    "REVIEW": {"bg": "#fff2db", "fg": "#8a4c00"},
    "HIGH": {"bg": "#fbe3e0", "fg": "#8f2424"},
    "READY": {"bg": "#dff1fb", "fg": "#0f5a85"},
}

RISK_COLORS = {
    "SAFE": "#198754",
    "REVIEW": "#e8960c",
    "HIGH": "#dc3545",
}

DATA_SOURCE_STYLES = {
    "synthguard-api": {"bg": "#dff1fb", "fg": "#0f5a85", "label": "SynthGuard API (Track 1)"},
    "biolens-heuristic": {"bg": "#fff2db", "fg": "#8a4c00", "label": "Local Heuristic Engine"},
    "biolens-offline": {"bg": "#eef2f4", "fg": "#475865", "label": "Offline Triage Engine"},
    "biolens-mock": {"bg": "#eef2f4", "fg": "#475865", "label": "Offline Triage Engine"},
    "biolens-demo": {"bg": "#eef2f4", "fg": "#475865", "label": "Demo Data"},
}

STATUS_STYLES = {
    "NEW": {"bg": "#e8eefc", "fg": "#284e9b"},
    "IN_REVIEW": {"bg": "#ece7fb", "fg": "#5c3aa6"},
    "ESCALATED": {"bg": "#fbe3e0", "fg": "#8f2424"},
    "CLEARED": {"bg": "#e6f5ee", "fg": "#1f6a4d"},
    "CLOSED": {"bg": "#eef2f4", "fg": "#475865"},
    "MOCK": {"bg": "#dff1fb", "fg": "#0f5a85"},
    "OFFLINE": {"bg": "#dff1fb", "fg": "#0f5a85"},
    "DEMO": {"bg": "#f7ead6", "fg": "#8c5521"},
    "INTEGRATED": {"bg": "#dfeee4", "fg": "#225f48"},
}

ACTION_STYLES = {
    "APPROVE": {"bg": "#e6f5ee", "fg": "#1f6a4d"},
    "MANUAL_REVIEW": {"bg": "#fff2db", "fg": "#8a4c00"},
    "ESCALATE": {"bg": "#fbe3e0", "fg": "#8f2424"},
    "HOLD": {"bg": "#ece7fb", "fg": "#5c3aa6"},
    "UNSET": {"bg": "#eef2f4", "fg": "#475865"},
    "OFFLINE": {"bg": "#eef2f4", "fg": "#475865"},
}
