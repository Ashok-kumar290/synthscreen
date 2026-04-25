from __future__ import annotations

import streamlit as st

from services import bootstrap_application, get_runtime_mode
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

mode = get_runtime_mode()
current_role = st.session_state.get("user_role", "Analyst")

render_hero(
    "Case Archive",
    "View resolved and finalized biosecurity screening cases. This read-only ledger provides the complete compliance history for all decisions.",
    mode,
)

render_global_sidebar()

resolved_cases = list_screenings(statuses=["CLEARED", "CLOSED"])

metrics = st.columns(3)
with metrics[0]:
    render_metric_card("Archived cases", str(len(resolved_cases)), "Fully resolved cases")
with metrics[1]:
    approved = sum(1 for c in resolved_cases if c["final_action"] == "APPROVE")
    render_metric_card("Approved", str(approved), "Cleared for synthesis")
with metrics[2]:
    held = sum(1 for c in resolved_cases if c["final_action"] == "HOLD")
    render_metric_card("Held / Rejected", str(held), "Synthesis blocked")

st.markdown("### Resolved Queue")
if not resolved_cases:
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
