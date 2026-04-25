from __future__ import annotations

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.constants import RISK_LEVELS
from services.sidebar import render_global_sidebar
from services.storage import list_screenings
from services.ui import (
    action_badge,
    apply_page_style,
    format_timestamp,
    render_hero,
    render_metric_card,
    risk_badge,
    status_badge,
)

st.set_page_config(page_title="BioLens Archive", layout="wide")
bootstrap_application()
apply_page_style()
render_global_sidebar()

mode = get_runtime_mode()
current_role = st.session_state.get("user_role", "Analyst")

render_hero(
    "Case Archive",
    "View resolved and finalized biosecurity screening cases. This read-only ledger provides the complete compliance history for all decisions.",
    mode,
    compact=True,
)

# ── Filters ────────────────────────────────────────────────────────────────────
filter_col, sort_col = st.columns([1.4, 0.6], gap="large")

with filter_col:
    fcols = st.columns([1.2, 1.0, 1.0])
    with fcols[0]:
        search_text = st.text_input(
            "Search",
            placeholder="Case ID prefix or category…",
            help="Matches against Case ID prefix or category (case-insensitive)",
        )
    with fcols[1]:
        selected_risks = st.multiselect("Risk Tier", list(RISK_LEVELS), default=[])
    with fcols[2]:
        selected_actions = st.multiselect(
            "Final Action", ["APPROVE", "HOLD", "MANUAL_REVIEW", "ESCALATE", "UNSET"], default=[]
        )

with sort_col:
    sort_choice = st.selectbox(
        "Sort by",
        ["Newest resolved first", "Oldest resolved first", "Highest hazard score", "Lowest hazard score"],
        index=0,
    )

sort_map = {
    "Newest resolved first": ("reviewed_at", True),
    "Oldest resolved first": ("reviewed_at", False),
    "Highest hazard score": ("hazard_score", True),
    "Lowest hazard score": ("hazard_score", False),
}
sort_col_name, sort_desc = sort_map[sort_choice]

resolved_cases = list_screenings(
    statuses=["CLEARED", "CLOSED"],
    risk_levels=list(selected_risks) if selected_risks else None,
    sort_by=sort_col_name,
    descending=sort_desc,
)

# Apply text search and action filter in-memory
if search_text.strip():
    q = search_text.strip().lower()
    resolved_cases = [
        c for c in resolved_cases
        if c["id"].lower().startswith(q) or q in c["category"].lower()
    ]

if selected_actions:
    # Normalise: UNSET means final_action is None
    resolved_cases = [
        c for c in resolved_cases
        if (c["final_action"] or "UNSET") in selected_actions
    ]

# ── Metrics ────────────────────────────────────────────────────────────────────
metrics = st.columns(4)
with metrics[0]:
    render_metric_card("Archived Cases", str(len(resolved_cases)), "Fully resolved cases")
with metrics[1]:
    approved = sum(1 for c in resolved_cases if c["final_action"] == "APPROVE")
    render_metric_card("Approved", str(approved), "Cleared for synthesis")
with metrics[2]:
    held = sum(1 for c in resolved_cases if c["final_action"] == "HOLD")
    render_metric_card("Held / Rejected", str(held), "Synthesis blocked")
with metrics[3]:
    high_archived = sum(1 for c in resolved_cases if c["risk_level"] == "HIGH")
    render_metric_card("HIGH Risk", str(high_archived), "Escalated cases resolved")

st.markdown("### Resolved Queue")
if not resolved_cases:
    if search_text or selected_risks or selected_actions:
        st.info("No archived cases match the current filters.")
    else:
        st.info("No resolved cases found. Go to the Inbox to review and clear active cases.")
else:
    for case in resolved_cases:
        card_col, action_col = st.columns([1.0, 0.24], gap="medium")
        with card_col:
            st.markdown(
                f"""
<div class="bl-case-card" style="opacity: 0.9;">
<div class="bl-case-row">
<div>
<div class="bl-case-title">Case {case['id'][:8]} • {case['category']}</div>
<div class="bl-case-meta">Resolved {format_timestamp(case['reviewed_at'] or case['submitted_at'])}</div>
</div>
<div class="bl-badge-row">
                            {risk_badge(case['risk_level'])}
                            {status_badge(case['analyst_status'])}
                            {action_badge(case['final_action'] or "UNSET")}
</div>
</div>
<div class="bl-case-meta">Score {case['hazard_score']:.2f} • Type {case['sequence_type']}</div>
</div>
                """,
                unsafe_allow_html=True,
            )
        with action_col:
            if st.button("View Log", key=f"archive-{case['id']}", use_container_width=True):
                st.session_state["selected_screening_id"] = case["id"]
                st.switch_page("pages/3_Review.py")
