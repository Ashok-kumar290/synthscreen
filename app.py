from __future__ import annotations

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.export import build_export_dataset, export_filename, export_screenings_csv, export_screenings_json
from services.seed_data import ensure_demo_cases
from services.storage import analytics_snapshot, list_screenings
from services.ui import (
    action_badge,
    apply_page_style,
    format_timestamp,
    render_hero,
    render_metric_card,
    risk_badge,
    status_badge,
)


st.set_page_config(page_title="BioLens", layout="wide")
bootstrap_application()
apply_page_style()

mode = get_runtime_mode()
snapshot = analytics_snapshot()
recent_cases = list_screenings(limit=5)
export_records = build_export_dataset()

render_hero(
    "BioLens",
    "Operational dashboard for function-aware biosecurity screening. Built for intake, triage, review, analytics, and reporting on top of the Synthscreen adapter layer.",
    mode,
)

metric_columns = st.columns(4)
with metric_columns[0]:
    render_metric_card("Sequences screened", str(snapshot["total"]), "Persisted local screenings")
with metric_columns[1]:
    render_metric_card("Flagged cases", str(snapshot["flagged"]), f"{snapshot['flagged_rate']:.0%} of total")
with metric_columns[2]:
    render_metric_card("Open review queue", str(snapshot["open_queue"]), "NEW, IN_REVIEW, or ESCALATED")
with metric_columns[3]:
    render_metric_card("Average hazard", f"{snapshot['average_hazard_score']:.2f}", "Across all saved cases")

sidebar_export_csv = export_screenings_csv(export_records)
sidebar_export_json = export_screenings_json(export_records)

with st.sidebar:
    st.subheader("Runtime")
    st.write(f"`BIOLENS_MODE={mode}`")
    if st.button("Load Demo Cases", use_container_width=True):
        result = ensure_demo_cases()
        st.success(f"Demo data synced. Inserted {result['inserted']} case(s).")

    st.subheader("Navigate")
    st.page_link("pages/1_Screening.py", label="Open Screening")
    st.page_link("pages/2_Inbox.py", label="Open Inbox")
    st.page_link("pages/3_Review.py", label="Open Review")
    st.page_link("pages/4_Analytics.py", label="Open Analytics")
    st.page_link("pages/5_Intelligence.py", label="Open Intelligence")

    st.subheader("Export")
    st.download_button(
        "Download All Cases (CSV)",
        data=sidebar_export_csv,
        file_name=export_filename("biolens_cases", "csv"),
        mime="text/csv",
        use_container_width=True,
    )
    st.download_button(
        "Download All Cases (JSON)",
        data=sidebar_export_json,
        file_name=export_filename("biolens_cases", "json"),
        mime="application/json",
        use_container_width=True,
    )

overview_left, overview_right = st.columns([1.15, 0.85], gap="large")

with overview_left:
    st.markdown("### Workflow")
    st.markdown(
        """
        <div class="bl-panel">
            <p><strong>1. Intake</strong><br>Paste a sequence or upload FASTA on the Screening page.</p>
            <p><strong>2. Triage</strong><br>BioLens calls the adapter and assigns a risk tier.</p>
            <p><strong>3. Review</strong><br>Flagged cases move into the inbox for analyst action.</p>
            <p><strong>4. Report</strong><br>Export the persisted record set as CSV or JSON.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Recent Cases")
    if not recent_cases:
        st.info("No screenings are stored yet. Start with the Screening page or load demo cases.")
    else:
        for case in recent_cases:
            st.markdown(
                f"""
                <div class="bl-case-card">
                    <div class="bl-case-row">
                        <div>
                            <div class="bl-case-title">Case {case['id'][:8]}</div>
                            <div class="bl-case-meta">{case['category']} • {format_timestamp(case['submitted_at'])}</div>
                        </div>
                        <div class="bl-badge-row">
                            {risk_badge(case['risk_level'])}
                            {status_badge(case['analyst_status'])}
                            {action_badge(case['final_action'] or "UNSET")}
                        </div>
                    </div>
                    <div class="bl-case-meta">Score {case['hazard_score']:.2f} • Confidence {case['confidence']:.2f} • Type {case['sequence_type']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

with overview_right:
    st.markdown("### Project Position")
    st.markdown(
        """
        <div class="bl-panel">
            <p><strong>Primary contribution:</strong> Synthscreen, the function-aware screening engine.</p>
            <p><strong>Operational layer:</strong> BioLens, the practitioner-facing dashboard and workflow tooling.</p>
            <p><strong>Deployment mode:</strong> local-first, SQLite-backed, and Docker packaged for offline demos and low-resource environments.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Acceptance Snapshot")
    st.markdown(
        f"""
        <div class="bl-panel">
            <p>{risk_badge('READY')} Screening, inbox, review, analytics, and export flows are present.</p>
            <p>{status_badge(mode.upper())} The adapter stays isolated behind <code>services/model_interface.py</code>.</p>
            <p>{action_badge('OFFLINE')} Docker and SQLite runtime files are included for local or demo use.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
