from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "biolens.db"

RUNTIME_MODES = ("offline", "online")
RISK_LEVELS = ("SAFE", "REVIEW", "HIGH")
ANALYST_STATUSES = ("NEW", "IN_REVIEW", "ESCALATED", "CLEARED", "CLOSED")
FINAL_ACTIONS = ("APPROVE", "MANUAL_REVIEW", "ESCALATE", "HOLD")

ALERT_SEVERITIES = ("LOW", "MEDIUM", "HIGH")
ALERT_SOURCE_TYPES = ("PUBLIC_HEALTH", "NEWS", "RESEARCH", "POLICY", "SURVEILLANCE", "MOCK")
ALERT_SIGNAL_TYPES = ("OUTBREAK_SIGNAL", "SURVEILLANCE_ANOMALY", "POLICY_UPDATE", "RESEARCH_SIGNAL", "SCREENING_RELEVANCE")
ALERT_STATUSES = ("NEW", "REVIEWED", "WATCHLISTED", "DISMISSED")

THREAT_POSTURE_LEVELS = ("NORMAL", "ELEVATED", "HIGH")
AUTOMATION_ACTIONS = ("AUTO_ESCALATE", "FLAG_FOR_REVIEW", "NOTIFY_SUPERVISOR")

RISK_STYLES = {
    "SAFE": {"bg": "#e6f5ee", "fg": "#1f6a4d"},
    "REVIEW": {"bg": "#fff2db", "fg": "#8a4c00"},
    "HIGH": {"bg": "#fbe3e0", "fg": "#8f2424"},
    "READY": {"bg": "#dff1fb", "fg": "#0f5a85"},
}

SEVERITY_STYLES = {
    "LOW": {"bg": "#dff1fb", "fg": "#0f5a85"},
    "MEDIUM": {"bg": "#fff2db", "fg": "#8a4c00"},
    "HIGH": {"bg": "#fbe3e0", "fg": "#8f2424"},
}

THREAT_POSTURE_STYLES = {
    "NORMAL": {"bg": "#e6f5ee", "fg": "#1f6a4d", "border": "#1f6a4d", "icon": "🟢", "label": "Normal Operations"},
    "ELEVATED": {"bg": "#fff2db", "fg": "#8a4c00", "border": "#e8960c", "icon": "🟡", "label": "Elevated Caution"},
    "HIGH": {"bg": "#fbe3e0", "fg": "#8f2424", "border": "#dc3545", "icon": "🔴", "label": "High Alert"},
}

RISK_COLORS = {
    "SAFE": "#198754",
    "REVIEW": "#e8960c",
    "HIGH": "#dc3545",
}

DATA_SOURCE_STYLES = {
    # Active data sources
    "synthguard-api": {"bg": "#dff1fb", "fg": "#0f5a85", "label": "SynthGuard API"},
    "biolens-offline": {"bg": "#eef2f4", "fg": "#475865", "label": "BioLens Heuristic"},
    # Legacy labels for historical records in the database
    "biolens-heuristic": {"bg": "#eef2f4", "fg": "#475865", "label": "BioLens Heuristic"},
    "biolens-mock": {"bg": "#eef2f4", "fg": "#475865", "label": "BioLens Heuristic"},
    "biolens-demo": {"bg": "#eef2f4", "fg": "#475865", "label": "BioLens Heuristic"},
}

STATUS_STYLES = {
    "NEW": {"bg": "#e8eefc", "fg": "#284e9b"},
    "IN_REVIEW": {"bg": "#ece7fb", "fg": "#5c3aa6"},
    "ESCALATED": {"bg": "#fbe3e0", "fg": "#8f2424"},
    "CLEARED": {"bg": "#e6f5ee", "fg": "#1f6a4d"},
    "CLOSED": {"bg": "#eef2f4", "fg": "#475865"},
    # Mode badges
    "OFFLINE": {"bg": "#eef2f4", "fg": "#475865"},
    "ONLINE": {"bg": "#dff1fb", "fg": "#0f5a85"},
    # Legacy mode badges (kept for any existing references)
    "MOCK": {"bg": "#eef2f4", "fg": "#475865"},
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

UI_MODES = ("compact", "full")

COMPACT_PAGES = [
    ("app.py", "Home"),
    ("pages/1_Screening.py", "Screening"),
    ("pages/2_Inbox.py", "Inbox"),
    ("pages/3_Review.py", "Review"),
]

FULL_PAGES = [
    ("app.py", "Home"),
    ("pages/1_Screening.py", "Screening"),
    ("pages/2_Inbox.py", "Inbox"),
    ("pages/3_Review.py", "Review"),
    ("pages/4_Analytics.py", "Analytics"),
    ("pages/5_Intelligence.py", "Intelligence"),
    ("pages/6_Archive.py", "Archive"),
    ("pages/7_Automation.py", "Automation"),
    ("pages/8_Reports.py", "Reports"),
]
