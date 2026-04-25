from __future__ import annotations

import os

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.dashboard import (
    compute_threat_posture,
    get_regional_threat_summary,
    get_response_time_metrics,
    get_unified_activity_feed,
)
from services.export import build_export_dataset, export_filename, export_screenings_csv, export_screenings_json
from services.intelligence import ensure_demo_alerts, list_alerts
from services.sidebar import render_global_sidebar
from services.storage import analytics_snapshot, list_screenings
from services.ui import (
    action_badge,
    apply_page_style,
    format_timestamp,
    render_hero,
    render_metric_card,
    render_regional_heatmap,
    render_response_time_chart,
    render_threat_posture_banner,
    render_unified_feed,
    risk_badge,
    status_badge,
)


st.set_page_config(page_title="BioLens", layout="wide")
bootstrap_application()
apply_page_style()

mode = get_runtime_mode()
snapshot = analytics_snapshot()
if not st.session_state.get("_demo_alerts_seeded"):
    ensure_demo_alerts()
    st.session_state["_demo_alerts_seeded"] = True
active_alerts = len([a for a in list_alerts() if a["status"] not in ("DISMISSED", "REVIEWED")])
recent_cases = list_screenings(limit=5)

current_role = st.session_state.get("user_role", "Analyst")

if current_role == "Supervisor":
    hero_title = "BioLens Supervisor Desk"
    hero_desc = "Review escalated cases, approve final synthesis authorizations, and audit analyst triage activity."
else:
    hero_title = "BioLens Analyst Triage"
    hero_desc = "Process inbound sequences, verify Synthscreen heuristics, and escalate flagged risk profiles."

render_hero(hero_title, hero_desc, mode)
render_global_sidebar()

# ── Threat Posture Banner ──────────────────────────────────────────────────────
posture = compute_threat_posture()
render_threat_posture_banner(posture)

# ── Metrics Row ────────────────────────────────────────────────────────────────
metric_columns = st.columns(5)
with metric_columns[0]:
    render_metric_card("Sequences Screened", str(snapshot["total"]), "All persisted cases")
with metric_columns[1]:
    render_metric_card("Flagged Cases", str(snapshot["flagged"]), f"{snapshot['flagged_rate']:.0%} of total")
with metric_columns[2]:
    render_metric_card("Open Review Queue", str(snapshot["open_queue"]), "NEW, IN_REVIEW, or ESCALATED")
with metric_columns[3]:
    render_metric_card("Active Intel Signals", str(active_alerts), "Unreviewed alerts")
with metric_columns[4]:
    render_metric_card("Avg Hazard Score", f"{snapshot['average_hazard_score']:.2f}", "Across all saved cases")

st.markdown("---")

# ── Operational View ───────────────────────────────────────────────────────────
left_col, right_col = st.columns([1.1, 0.9], gap="large")

with left_col:
    st.markdown("### Live Activity Feed")
    st.caption("Unified view of recent screenings and intelligence alerts, ordered by time.")
    feed_items = get_unified_activity_feed(limit=18)
    render_unified_feed(feed_items)

with right_col:
    st.markdown("### Regional Threat Map")
    st.caption("Active alert distribution by region, severity-weighted.")
    regional_data = get_regional_threat_summary()
    render_regional_heatmap(regional_data)

st.markdown("---")

# ── Bottom Row ─────────────────────────────────────────────────────────────────
bottom_left, bottom_right = st.columns([1.2, 0.8], gap="large")

with bottom_left:
    st.markdown("### Response Time")
    st.caption("Mean time from case creation to closure, by risk tier (resolved cases).")
    rt_metrics = get_response_time_metrics()
    render_response_time_chart(rt_metrics)

with bottom_right:
    st.markdown("### Workflow")
    st.markdown(
        """
<div class="bl-panel">
    <p><strong>1. Intake</strong><br>Paste a sequence or upload FASTA on the Screening page.</p>
    <p><strong>2. Triage</strong><br>BioLens calls the adapter, assigns a risk tier, and checks the intelligence watchlist.</p>
    <p><strong>3. Review</strong><br>Flagged cases move into the inbox for analyst action — auto-rules may pre-escalate.</p>
    <p><strong>4. Report</strong><br>Export persisted records or generate a compliance report from the Reports page.</p>
</div>
        """,
        unsafe_allow_html=True,
    )

    if current_role == "Supervisor":
        st.markdown("### Quick Actions")
        qcol1, qcol2 = st.columns(2)
        with qcol1:
            if st.button("📥 View Escalated", use_container_width=True):
                st.switch_page("pages/2_Inbox.py")
        with qcol2:
            if st.button("📡 View Alerts", use_container_width=True):
                st.switch_page("pages/5_Intelligence.py")
