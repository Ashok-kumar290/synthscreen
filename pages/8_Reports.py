from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.dashboard import compute_threat_posture, get_response_time_metrics
from services.intelligence import get_alert_statistics, list_alerts, list_watchlist
from services.sidebar import render_global_sidebar
from services.storage import analytics_snapshot, get_cases_in_range, get_alerts_in_range
from services.ui import apply_page_style, render_hero, render_metric_card


st.set_page_config(page_title="BioLens — Reports", layout="wide")
bootstrap_application()
apply_page_style()
render_global_sidebar()

mode = get_runtime_mode()
render_hero(
    "Compliance Reports",
    "Generate structured operational reports summarising screening activity, intelligence coverage, and case resolution for compliance and audit purposes.",
    mode,
)

current_role = st.session_state.get("user_role", "Analyst")

# ── Report Parameters ──────────────────────────────────────────────────────────
param_col, _ = st.columns([1.2, 0.8])
with param_col:
    today = datetime.now(timezone.utc).date()
    preset = st.selectbox(
        "Report Period",
        ["Today", "Last 7 Days", "Last 30 Days", "Custom Range"],
        index=1,
    )
    if preset == "Today":
        start_date = today
        end_date = today
    elif preset == "Last 7 Days":
        start_date = today - timedelta(days=6)
        end_date = today
    elif preset == "Last 30 Days":
        start_date = today - timedelta(days=29)
        end_date = today
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            start_date = st.date_input("From", value=today - timedelta(days=6))
        with col_b:
            end_date = st.date_input("To", value=today)

    report_title = st.text_input("Report Title", value=f"BioLens Operational Report — {start_date} to {end_date}")
    generate = st.button("⚙️ Generate Report", type="primary")

if not generate:
    st.info("Select a report period and click **Generate Report**.")
    st.stop()

# ── Data Collection ────────────────────────────────────────────────────────────
start_str = start_date.isoformat()
end_str = end_date.isoformat()

cases = get_cases_in_range(start_str, end_str)
alerts_in_range = get_alerts_in_range(start_str, end_str)
all_alerts = list_alerts()
active_watchlist = list_watchlist(active_only=True)
intel_stats = get_alert_statistics()
posture = compute_threat_posture()
rt_metrics = get_response_time_metrics()
snapshot = analytics_snapshot()

# ── Summary Metrics ────────────────────────────────────────────────────────────
st.markdown(f"## {report_title}")
st.caption(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} · Period: {start_str} → {end_str} · Mode: {mode.upper()}")

m1, m2, m3, m4 = st.columns(4)
with m1:
    render_metric_card("Cases in Period", str(len(cases)), "All screened cases")
with m2:
    flagged = sum(1 for c in cases if c["risk_level"] in ("REVIEW", "HIGH"))
    render_metric_card("Flagged", str(flagged), f"{flagged/len(cases):.0%} of total" if cases else "0%")
with m3:
    cleared = sum(1 for c in cases if c["analyst_status"] in ("CLEARED", "CLOSED"))
    render_metric_card("Resolved", str(cleared), "CLEARED or CLOSED")
with m4:
    render_metric_card("New Alerts", str(len(alerts_in_range)), "Intelligence alerts in period")

st.markdown("---")

# ── Section 1: Screening Summary ───────────────────────────────────────────────
st.markdown("### 1. Screening Summary")
if not cases:
    st.info("No cases were screened in this period.")
else:
    risk_counts = {"SAFE": 0, "REVIEW": 0, "HIGH": 0}
    for c in cases:
        risk_counts[c["risk_level"]] = risk_counts.get(c["risk_level"], 0) + 1

    status_counts: dict[str, int] = {}
    for c in cases:
        status_counts[c["analyst_status"]] = status_counts.get(c["analyst_status"], 0) + 1

    action_counts: dict[str, int] = {}
    for c in cases:
        act = c.get("final_action") or "UNSET"
        action_counts[act] = action_counts.get(act, 0) + 1

    st.markdown(
        f"""
| Metric | Count |
|--------|-------|
| Total Cases | {len(cases)} |
| SAFE | {risk_counts.get('SAFE', 0)} |
| REVIEW | {risk_counts.get('REVIEW', 0)} |
| HIGH | {risk_counts.get('HIGH', 0)} |
| Cleared / Closed | {cleared} |
| Open / In Review | {sum(1 for c in cases if c['analyst_status'] in ('NEW', 'IN_REVIEW'))} |
| Escalated | {sum(1 for c in cases if c['analyst_status'] == 'ESCALATED')} |
        """
    )

# ── Section 2: Intelligence Summary ───────────────────────────────────────────
st.markdown("### 2. Intelligence Summary")
st.markdown(
    f"""
| Metric | Count |
|--------|-------|
| New Alerts in Period | {len(alerts_in_range)} |
| Total Active Alerts (all-time) | {len([a for a in all_alerts if a['status'] not in ('DISMISSED', 'REVIEWED')])} |
| HIGH Severity Alerts | {len([a for a in alerts_in_range if a['severity'] == 'HIGH'])} |
| Active Watchlist Items | {len(active_watchlist)} |
| Total Case–Alert Links | {intel_stats.get('total_case_links', 0)} |
| Current Threat Posture | {posture['level']} (Score: {posture['score']}/100) |
    """
)

if alerts_in_range:
    st.markdown("**Alerts generated in this period:**")
    for a in alerts_in_range:
        st.markdown(f"- [{a['severity']}] **{a['title']}** · {a['source_name']} · {a['region']} · Status: {a['status']}")

# ── Section 3: Response Times ──────────────────────────────────────────────────
st.markdown("### 3. Response Time Summary")
if rt_metrics.get("overall"):
    overall = rt_metrics["overall"]
    st.markdown(
        f"""
| Metric | Value |
|--------|-------|
| Mean Response Time | {overall.get('mean_hours', 0):.1f} hours |
| Median Response Time | {overall.get('median_hours', 0):.1f} hours |
| P90 Response Time | {overall.get('p90_hours', 0):.1f} hours |
| Resolved Cases Measured | {overall.get('count', 0)} |
        """
    )
    for risk, stats in rt_metrics.get("by_risk", {}).items():
        if stats:
            st.markdown(f"- **{risk}**: Mean {stats.get('mean_hours', 0):.1f}h, P90 {stats.get('p90_hours', 0):.1f}h (n={stats.get('count', 0)})")
else:
    st.info("No response time data available for this period.")

# ── Section 4: Watchlist Activity ─────────────────────────────────────────────
st.markdown("### 4. Watchlist Activity")
if active_watchlist:
    for item in active_watchlist:
        st.markdown(f"- **{item['keyword']}** ({item['category']}) · Region: {item['region']} · Priority: {item['priority']}")
else:
    st.info("No active watchlist items.")

# ── Section 5: Compliance Notes ───────────────────────────────────────────────
st.markdown("### 5. Compliance Notes")
st.markdown(
    """
- All screening decisions are persisted with full audit trails in the local SQLite database.
- Role-based access control is enforced — HIGH risk cases require Supervisor approval.
- Intelligence alerts are sourced from external feeds and operator-authored signals.
- Export this report as Markdown or download raw case data from the Inbox page.
    """
)

st.markdown("---")

# ── Export ────────────────────────────────────────────────────────────────────
st.markdown("### Export")
export_cols = st.columns(2)

report_md = f"""# {report_title}

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Period:** {start_str} → {end_str}
**Mode:** {mode.upper()}

## 1. Screening Summary
- Total cases: {len(cases)}
- Flagged: {flagged} ({flagged/len(cases):.0%})
- Resolved: {cleared}

## 2. Intelligence Summary
- New alerts: {len(alerts_in_range)}
- Active watchlist items: {len(active_watchlist)}
- Threat posture: {posture['level']} ({posture['score']}/100)

## 3. Response Times
- Mean: {rt_metrics.get('overall', {}).get('mean_hours', 'N/A')} hours

## 4. Compliance Notes
All decisions persisted with audit trails. Role-based access enforced.
"""

with export_cols[0]:
    st.download_button(
        "⬇️ Download Report (Markdown)",
        data=report_md.encode("utf-8"),
        file_name=f"biolens_report_{start_str}_{end_str}.md",
        mime="text/markdown",
        use_container_width=True,
    )

with export_cols[1]:
    report_json = {
        "title": report_title,
        "period": {"start": start_str, "end": end_str},
        "generated_at": datetime.now().isoformat(),
        "mode": mode,
        "screening_summary": {"total": len(cases), "flagged": flagged, "resolved": cleared},
        "intelligence_summary": {
            "new_alerts": len(alerts_in_range),
            "active_watchlist": len(active_watchlist),
            "posture": posture,
        },
        "response_times": rt_metrics.get("overall"),
    }
    st.download_button(
        "⬇️ Download Report (JSON)",
        data=json.dumps(report_json, indent=2).encode("utf-8"),
        file_name=f"biolens_report_{start_str}_{end_str}.json",
        mime="application/json",
        use_container_width=True,
    )
