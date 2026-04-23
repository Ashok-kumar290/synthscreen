from __future__ import annotations

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.constants import ANALYST_STATUSES, RISK_LEVELS
from services.export import build_export_dataset, export_filename, export_screenings_csv, export_screenings_json
from services.storage import list_screenings
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

mode = get_runtime_mode()
render_hero(
    "Case Inbox",
    "Review the saved screening queue, filter by operational state, sort by priority, and route a case into detailed review.",
    mode,
)

filters_col, export_col = st.columns([1.2, 0.8], gap="large")

with filters_col:
    selected_statuses = st.multiselect("Analyst status", ANALYST_STATUSES, default=[])
    selected_risks = st.multiselect("Risk tier", RISK_LEVELS, default=[])

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
if not cases:
    st.info("No cases match the current filters.")
else:
    for case in cases:
        card_col, action_col = st.columns([1.0, 0.24], gap="medium")
        with card_col:
            sequence_preview = f"{case['sequence_text'][:72]}..." if len(case["sequence_text"]) > 72 else case["sequence_text"]
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
