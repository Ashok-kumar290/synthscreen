from __future__ import annotations

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.constants import ANALYST_STATUSES, RISK_LEVELS
from services.sidebar import render_global_sidebar
from services.export import build_export_dataset, export_filename, export_screenings_csv, export_screenings_json
from services.storage import list_screenings
from services.intelligence import get_case_intelligence
from services.ui import (
    apply_page_style,
    format_timestamp,
    render_hero,
    render_metric_card,
    risk_badge,
    status_badge,
)


st.set_page_config(page_title="BioLens Inbox", layout="wide")
bootstrap_application()
apply_page_style()
render_global_sidebar()

mode = get_runtime_mode()
render_hero(
    "Case Inbox",
    "Review the saved screening queue, filter by operational state, sort by priority, and route a case into detailed review.",
    mode,
)

current_role = st.session_state.get("user_role", "Analyst")
is_supervisor = current_role == "Supervisor"

# Default filters based on role
if is_supervisor:
    default_statuses = ["ESCALATED"]
else:
    default_statuses = ["NEW", "IN_REVIEW"]

filters_col, export_col = st.columns([1.2, 0.8], gap="large")

with filters_col:
    selected_statuses = st.multiselect("Analyst status", ANALYST_STATUSES, default=default_statuses)
    selected_risks = st.multiselect("Risk tier", RISK_LEVELS, default=[])
    intel_only = st.checkbox("⚡ Has Intel Context", value=False, help="Show only cases linked to intelligence alerts")

with export_col:
    sort_choice = st.selectbox(
        "Sort queue by",
        ["Newest first", "Oldest first", "Risk score", "Confidence"],
        index=0,
    )

sort_options = {
    "Newest first": ("submitted_at", True),
    "Oldest first": ("submitted_at", False),
    "Risk score": ("hazard_score", True),
    "Confidence": ("confidence", True),
}

sort_by, descending = sort_options[sort_choice]
cases = list_screenings(
    statuses=list(selected_statuses) or None,
    risk_levels=list(selected_risks) or None,
    sort_by=sort_by,
    descending=descending,
)

# Build intel lookup if needed
if intel_only:
    intel_case_ids = set()
    for case in cases:
        links = get_case_intelligence(case["id"])
        if links:
            intel_case_ids.add(case["id"])
    cases = [c for c in cases if c["id"] in intel_case_ids]

# Pre-fetch intel links for badge rendering (only first 50 to avoid slowdown)
_intel_flag_ids: set[str] = set()
for case in cases[:50]:
    if get_case_intelligence(case["id"]):
        _intel_flag_ids.add(case["id"])

filtered_export = build_export_dataset([case["id"] for case in cases])

metrics = st.columns(3)
with metrics[0]:
    render_metric_card("Visible cases", str(len(cases)), "Current filtered queue")
with metrics[1]:
    flagged = sum(1 for case in cases if case["risk_level"] in {"REVIEW", "HIGH"})
    render_metric_card("Flagged in view", str(flagged), "REVIEW or HIGH")
with metrics[2]:
    actionable = sum(1 for case in cases if case["analyst_status"] in {"NEW", "IN_REVIEW", "ESCALATED"})
    render_metric_card("Needs action", str(actionable), "Open analyst workload")

download_cols = st.columns(2)
with download_cols[0]:
    st.download_button(
        "Download Filtered CSV",
        data=export_screenings_csv(filtered_export),
        file_name=export_filename("biolens_filtered", "csv"),
        mime="text/csv",
        use_container_width=True,
    )
with download_cols[1]:
    st.download_button(
        "Download Filtered JSON",
        data=export_screenings_json(filtered_export),
        file_name=export_filename("biolens_filtered", "json"),
        mime="application/json",
        use_container_width=True,
    )

st.markdown("### Queue")

# Quick Actions bar
action_cols = st.columns(3)
with action_cols[0]:
    if not is_supervisor:
        safe_ids = [c["id"] for c in cases if c["risk_level"] == "SAFE" and c["analyst_status"] in ("NEW", "IN_REVIEW")]
        if st.button(f"✅ Approve All SAFE ({len(safe_ids)})", disabled=len(safe_ids) == 0, use_container_width=True):
            from services.storage import bulk_update_status
            bulk_update_status(safe_ids, "CLEARED", "APPROVE")
            st.toast(f"Approved {len(safe_ids)} SAFE cases.", icon="✅")
            st.rerun()
    else:
        esc_ids = [c["id"] for c in cases if c["analyst_status"] == "ESCALATED"]
        if st.button(f"✅ Approve All ESCALATED ({len(esc_ids)})", disabled=len(esc_ids) == 0, use_container_width=True):
            from services.storage import bulk_update_status
            bulk_update_status(esc_ids, "CLEARED", "APPROVE")
            st.toast(f"Approved {len(esc_ids)} ESCALATED cases.", icon="✅")
            st.rerun()

with action_cols[1]:
    if not is_supervisor:
        high_ids = [c["id"] for c in cases if c["risk_level"] == "HIGH" and c["analyst_status"] in ("NEW", "IN_REVIEW")]
        if st.button(f"🚨 Escalate All HIGH ({len(high_ids)})", disabled=len(high_ids) == 0, use_container_width=True):
            from services.storage import bulk_update_status
            bulk_update_status(high_ids, "ESCALATED", "ESCALATE")
            st.toast(f"Escalated {len(high_ids)} HIGH cases.", icon="🚨")
            st.rerun()

with action_cols[2]:
    st.metric("Queue Depth", len(cases))


if not cases:
    st.info("No cases match the current filters.")
else:
    for case in cases:
        card_col, action_col = st.columns([1.0, 0.24], gap="medium")
        with card_col:
            sequence_preview = f"{case['sequence_text'][:72]}..." if len(case["sequence_text"]) > 72 else case["sequence_text"]
            has_intel = case["id"] in _intel_flag_ids
            intel_badge_html = (
                '<span style="background:#fff8e1; border:1px solid #f39c12; border-radius:999px; '
                'font-size:0.72rem; font-weight:700; padding:0.15rem 0.55rem; color:#8a4c00;">⚡ INTEL</span>'
                if has_intel else ""
            )
            st.markdown(
                f"""
<div class="bl-case-card">
<div class="bl-case-row">
<div>
<div class="bl-case-title">Case {case['id'][:8]} • {case['category']}</div>
<div class="bl-case-meta">{format_timestamp(case['submitted_at'])} • {case['sequence_type']}</div>
</div>
<div class="bl-badge-row">
                            {risk_badge(case['risk_level'])}
                            {status_badge(case['analyst_status'])}
                            {intel_badge_html}
</div>
</div>
<div class="bl-case-meta">Score {case['hazard_score']:.2f} • Confidence {case['confidence']:.2f}</div>
<p>{case['explanation']}</p>
<div class="bl-sequence-preview">{sequence_preview}</div>
</div>
                """,
                unsafe_allow_html=True,
            )
        with action_col:
            if st.button("Review", key=f"review-{case['id']}", use_container_width=True):
                st.session_state["selected_screening_id"] = case["id"]
                st.switch_page("pages/3_Review.py")
