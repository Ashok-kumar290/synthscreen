from __future__ import annotations

import json

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.constants import ANALYST_STATUSES, FINAL_ACTIONS
from services.export import build_export_dataset, export_filename, export_screenings_csv, export_screenings_json
from services.storage import get_screening, list_audit_events, list_screenings, update_review
from services.ui import (
    action_badge,
    apply_page_style,
    format_timestamp,
    render_hero,
    render_metric_card,
    risk_badge,
    status_badge,
    render_threat_radar,
    render_attributed_sequence,
    render_verdict_strip,
)


st.set_page_config(page_title="BioLens Review", layout="wide")
bootstrap_application()
apply_page_style()

mode = get_runtime_mode()
all_cases = list_screenings(limit=250)

render_hero(
    "Case Review",
    "Inspect an individual screening record, update analyst state, capture notes and final action, then export the reviewed case with its audit trail.",
    mode,
)

if not all_cases:
    st.info("No cases are available for review yet. Save a result from Screening or load demo cases.")
    st.stop()

case_lookup = {
    f"{case['id'][:8]} • {case['risk_level']} • {case['category']} • {format_timestamp(case['submitted_at'])}": case["id"]
    for case in all_cases
}

selected_id = st.session_state.get("selected_screening_id")
if selected_id not in case_lookup.values():
    selected_id = all_cases[0]["id"]

selected_label = next(label for label, case_id in case_lookup.items() if case_id == selected_id)
selected_label = st.selectbox("Choose case", list(case_lookup.keys()), index=list(case_lookup.keys()).index(selected_label))
selected_id = case_lookup[selected_label]
st.session_state["selected_screening_id"] = selected_id

case = get_screening(selected_id)
audit_events = list_audit_events(selected_id)
export_record = build_export_dataset([selected_id])

st.markdown(render_verdict_strip(case).replace("\n", " "), unsafe_allow_html=True)

header_cols = st.columns(2)
with header_cols[0]:
    render_metric_card("Submitted", format_timestamp(case["submitted_at"]), case["sequence_type"])
with header_cols[1]:
    reviewed_label = format_timestamp(case["reviewed_at"]) if case["reviewed_at"] else "Pending"
    render_metric_card("Reviewed", reviewed_label, case["analyst_status"])

detail_col, review_col = st.columns([1.1, 0.9], gap="large")

with detail_col:
    card_html = f"""
<div class="bl-case-card">
<div class="bl-case-row">
<div>
<div class="bl-case-title">Case {case['id']}</div>
<div class="bl-case-meta">{case['category']}</div>
</div>
<div class="bl-badge-row">
                    {risk_badge(case['risk_level'])}
                    {status_badge(case['analyst_status'])}
                    {action_badge(case['final_action'] or 'UNSET')}
</div>
</div>
<p>{case['explanation']}</p>
</div>
        """
    st.markdown(card_html.replace("\n", " "), unsafe_allow_html=True)
    if case.get("threat_breakdown"):
        st.markdown("#### Structured Threat Assessment")
        render_threat_radar(case["threat_breakdown"])
        
    st.markdown("#### Sequence")
    st.caption(f"{len(case['sequence_text'])} characters • {case['sequence_type']}")
    render_attributed_sequence(case["sequence_text"], case.get("attribution_data"))

    st.markdown("#### Baseline Comparison")
    st.write(case["baseline_result"] or "No baseline comparison is stored for this case.")

    st.markdown("#### Export")
    export_cols = st.columns(2)
    with export_cols[0]:
        st.download_button(
            "Download Case CSV",
            data=export_screenings_csv(export_record),
            file_name=export_filename(f"case_{case['id'][:8]}", "csv"),
            mime="text/csv",
            use_container_width=True,
        )
    with export_cols[1]:
        st.download_button(
            "Download Case JSON",
            data=export_screenings_json(export_record),
            file_name=export_filename(f"case_{case['id'][:8]}", "json"),
            mime="application/json",
            use_container_width=True,
        )

with review_col:
    st.markdown("#### Analyst Decision")
    action_options = ["UNSET"] + list(FINAL_ACTIONS)
    with st.form("review-form"):
        analyst_status = st.selectbox(
            "Analyst status",
            ANALYST_STATUSES,
            index=list(ANALYST_STATUSES).index(case["analyst_status"]),
        )
        final_action = st.selectbox(
            "Final action",
            action_options,
            index=action_options.index(case["final_action"] or "UNSET"),
        )
        analyst_notes = st.text_area(
            "Analyst notes",
            value=case["analyst_notes"] or "",
            height=220,
            placeholder="Capture rationale, follow-up steps, or escalation notes.",
        )
        saved = st.form_submit_button("Save Review Update", type="primary", use_container_width=True)

    if saved:
        update_review(
            screening_id=selected_id,
            analyst_status=analyst_status,
            analyst_notes=analyst_notes,
            final_action=None if final_action == "UNSET" else final_action,
        )
        st.success("Review state updated.")
        st.rerun()

    st.markdown("#### Audit Trail")
    if not audit_events:
        st.info("No audit events are recorded for this case yet.")
    else:
        for event in audit_events:
            detail_text = json.dumps(event["details"], ensure_ascii=True)
            st.markdown(
                f"""
<div class="bl-panel bl-audit-entry">
<strong>{event['event_type']}</strong><br>
<span class="bl-case-meta">{format_timestamp(event['event_time'])}</span>
<div class="bl-audit-text">{detail_text}</div>
</div>
                """,
                unsafe_allow_html=True,
            )
