from __future__ import annotations

import html
import json

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.constants import ANALYST_STATUSES, FINAL_ACTIONS
from services.sidebar import render_global_sidebar
from services.export import build_export_dataset, export_filename, export_screenings_csv, export_screenings_json
from services.intelligence import get_case_intelligence
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
    render_primary_risk_drivers,
    render_threat_bars,
)


st.set_page_config(page_title="BioLens Review", layout="wide")
bootstrap_application()
apply_page_style()
render_global_sidebar()

mode = get_runtime_mode()
all_cases = list_screenings(limit=250)

render_hero(
    "Case Review",
    "Inspect an individual screening record, update analyst state, capture notes and final action, then export the reviewed case with its audit trail.",
    mode,
    compact=True,
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
intel_links = get_case_intelligence(selected_id)
export_record = build_export_dataset([selected_id])

st.markdown(render_verdict_strip(case).replace("\n", " "), unsafe_allow_html=True)

header_cols = st.columns(2, gap="large")
with header_cols[0]:
    render_metric_card("Submitted", format_timestamp(case["submitted_at"]), case["sequence_type"])
with header_cols[1]:
    reviewed_label = format_timestamp(case["reviewed_at"]) if case["reviewed_at"] else "Pending"
    render_metric_card("Reviewed", reviewed_label, case["analyst_status"])

detail_col, review_col = st.columns([1.4, 0.6], gap="large")

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
        col1, col2 = st.columns([1.0, 1.2], gap="large")
        with col1:
            st.markdown("#### Threat Radar")
            render_threat_radar(case["threat_breakdown"], height=260)
        with col2:
            st.markdown("#### Structured Assessment")
            render_threat_bars(case["threat_breakdown"], top_margin="4.5rem")

        st.markdown("#### Primary Risk Drivers")
        render_primary_risk_drivers(case["threat_breakdown"])
        
    st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    st.markdown("#### Sequence")
    st.caption(f"{len(case['sequence_text'])} characters • {case['sequence_type']}")
    render_attributed_sequence(case["sequence_text"], case.get("attribution_data"))

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
    
    role = st.session_state.get("user_role", "Analyst")
    is_supervisor = role == "Supervisor"

    if case["risk_level"] == "HIGH" and not is_supervisor:
        st.warning("⚠️ **HIGH** risk cases require Supervisor approval. You may only Escalate.")
        available_statuses = ("NEW", "IN_REVIEW", "ESCALATED")
        available_actions = ("UNSET", "ESCALATE", "HOLD")
    else:
        available_statuses = ANALYST_STATUSES
        available_actions = ("UNSET",) + FINAL_ACTIONS

    with st.form("review-form"):
        current_status = case["analyst_status"] if case["analyst_status"] in available_statuses else available_statuses[0]
        analyst_status = st.selectbox(
            "Analyst status",
            available_statuses,
            index=list(available_statuses).index(current_status),
        )
        
        current_action = (case["final_action"] or "UNSET") if (case["final_action"] or "UNSET") in available_actions else available_actions[0]
        final_action = st.selectbox(
            "Final action",
            available_actions,
            index=list(available_actions).index(current_action),
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

    st.markdown("#### Baseline Comparison")
    st.write(case["baseline_result"] or "No baseline comparison is stored for this case.")
    
    st.markdown("#### Linked Intelligence Context")
    if not intel_links:
        st.write("No external intelligence signals linked to this case.")
    else:
        for link in intel_links:
            priority_color = "#e74c3c" if link["priority"] == "HIGH" else "#f39c12" if link["priority"] == "MEDIUM" else "#3498db"
            st.markdown(f"""
            <div style="background: rgba(243, 156, 18, 0.05); border-left: 4px solid #f39c12; border-radius: 6px; padding: 1rem; margin-bottom: 1rem;">
                <div style="font-weight: 600; color: #d35400; margin-bottom: 0.4rem; font-size: 1.05rem;">{html.escape(link['title'])}</div>
                <div style="font-size: 0.85rem; color: var(--bl-muted); margin-bottom: 0.8rem;">
                    <strong>Alert ID:</strong> {link['alert_id']} | <strong>Region:</strong> {link['region']} | 
                    <strong>Severity:</strong> {link['severity']} | <strong>Confidence:</strong> {link['confidence']}%
                </div>
                <div style="font-size: 0.9rem; margin-bottom: 0.5rem;"><strong>Watchlist Match:</strong> {html.escape(link['keyword'])} ({html.escape(link['w_category'])})</div>
                <div style="font-size: 0.85rem; color: {priority_color}; font-weight: bold; margin-bottom: 0.5rem;">Impact: {link['priority']} Priority</div>
                <div style="font-size: 0.85rem; background: rgba(255,255,255,0.5); padding: 0.5rem; border-radius: 4px;">
                    <strong>Relevance:</strong> {html.escape(link['screening_relevance'])}<br>
                    <strong>Action:</strong> {html.escape(link['suggested_action'])}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("#### Audit Trail")
    if not audit_events:
        st.info("No audit events are recorded for this case yet.")
    else:
        for event in audit_events:
            if event['event_type'] == "case_created":
                icon = "📥"
            elif event['event_type'] == "status_change":
                icon = "🔄"
            elif event['event_type'] == "action_set":
                icon = "⚖️"
            else:
                icon = "📝"

            detail_text = json.dumps(event["details"], ensure_ascii=True)
            st.markdown(
                f"""
<div style="display: flex; gap: 1rem; margin-bottom: 1rem; align-items: flex-start;">
    <div style="font-size: 1.5rem; background: var(--bl-surface); border: 1px solid var(--bl-border); border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">{icon}</div>
    <div class="bl-panel bl-audit-entry" style="flex-grow: 1; margin: 0;">
        <div style="display: flex; justify-content: space-between;">
            <strong>{event['event_type'].replace('_', ' ').title()}</strong>
            <span class="bl-case-meta">{format_timestamp(event['event_time'])}</span>
        </div>
        <div class="bl-audit-text" style="margin-top: 0.5rem; color: var(--bl-muted);">{detail_text}</div>
    </div>
</div>
                """,
                unsafe_allow_html=True,
            )
