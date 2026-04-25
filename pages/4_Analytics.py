from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.dashboard import get_response_time_metrics
from services.intelligence import get_alert_statistics, get_alert_timeline, get_watchlist_effectiveness
from services.sidebar import render_global_sidebar
from services.storage import analytics_snapshot, response_time_distribution
from services.ui import apply_page_style, render_hero, render_metric_card, render_response_time_chart


st.set_page_config(page_title="BioLens Analytics", layout="wide")
bootstrap_application()
apply_page_style()
render_global_sidebar()

mode = get_runtime_mode()
snapshot = analytics_snapshot()
intel_stats = get_alert_statistics()

render_hero(
    "Analytics",
    "Operational metrics from persisted SQLite records, correlated with active intelligence signals for a unified picture of biosecurity activity.",
    mode,
)

# ── Top metrics ────────────────────────────────────────────────────────────────
metric_cols = st.columns(5)
with metric_cols[0]:
    render_metric_card("Total Screened", str(snapshot["total"]), "All persisted cases")
with metric_cols[1]:
    render_metric_card("Flagged Rate", f"{snapshot['flagged_rate']:.0%}", "REVIEW or HIGH")
with metric_cols[2]:
    render_metric_card("Open Queue", str(snapshot["open_queue"]), "Cases awaiting closure")
with metric_cols[3]:
    render_metric_card("Avg Hazard", f"{snapshot['average_hazard_score']:.2f}", "Mean risk score")
with metric_cols[4]:
    render_metric_card("Intel Alerts", str(intel_stats["total"]), f"{intel_stats['active_watchlist_count']} watchlisted")

st.markdown("---")

# ── Screening analytics ────────────────────────────────────────────────────────
st.markdown("### Screening Overview")

risk_df = pd.DataFrame(snapshot["risk_distribution"])
status_df = pd.DataFrame(snapshot["status_distribution"])
activity_df = pd.DataFrame(snapshot["activity_over_time"])
category_df = pd.DataFrame(snapshot["top_categories"])

upper_left, upper_right = st.columns(2, gap="large")
with upper_left:
    st.markdown("#### Risk Distribution")
    if risk_df.empty:
        st.info("No screening data available.")
    else:
        colors = {"HIGH": "#dc3545", "REVIEW": "#e8960c", "SAFE": "#198754"}
        fig = go.Figure(go.Bar(
            x=risk_df["risk_level"],
            y=risk_df["count"],
            marker_color=[colors.get(r, "#8899a6") for r in risk_df["risk_level"]],
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=260, margin=dict(l=10, r=10, t=10, b=30),
            yaxis=dict(gridcolor="rgba(0,0,0,0.05)"), xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig, use_container_width=True)

with upper_right:
    st.markdown("#### Status Distribution")
    if status_df.empty:
        st.info("No review state available yet.")
    else:
        st.bar_chart(status_df, x="analyst_status", y="count")

lower_left, lower_right = st.columns(2, gap="large")
with lower_left:
    st.markdown("#### Activity Over Time")
    if activity_df.empty:
        st.info("No activity recorded yet.")
    else:
        activity_df["day"] = pd.to_datetime(activity_df["day"])
        st.line_chart(activity_df.set_index("day")["count"])

with lower_right:
    st.markdown("#### Top Flagged Categories")
    if category_df.empty:
        st.info("No flagged categories available yet.")
    else:
        st.bar_chart(category_df, x="category", y="count")

st.markdown("---")

# ── Intelligence Correlation ───────────────────────────────────────────────────
st.markdown("### Intelligence Correlation")
st.caption("Overlay screening volume with intelligence alert creation to spot outbreak-driven screening spikes.")

timeline = get_alert_timeline()
intel_timeline_df = pd.DataFrame(timeline) if timeline else pd.DataFrame(columns=["day", "count", "high_count"])

if not activity_df.empty:
    corr_fig = go.Figure()
    corr_fig.add_trace(go.Bar(
        x=activity_df["day"],
        y=activity_df["count"],
        name="Screenings / Day",
        marker_color="rgba(15, 90, 133, 0.6)",
        yaxis="y",
    ))
    if not intel_timeline_df.empty:
        intel_timeline_df["day"] = pd.to_datetime(intel_timeline_df["day"])
        corr_fig.add_trace(go.Scatter(
            x=intel_timeline_df["day"],
            y=intel_timeline_df["count"],
            name="New Alerts / Day",
            mode="lines+markers",
            line=dict(color="#dc3545", width=2),
            marker=dict(size=6),
            yaxis="y2",
        ))
    corr_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=280,
        margin=dict(l=10, r=60, t=10, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        yaxis=dict(title="Screenings", gridcolor="rgba(0,0,0,0.05)", side="left"),
        yaxis2=dict(title="New Alerts", overlaying="y", side="right", showgrid=False),
        xaxis=dict(showgrid=False),
    )
    st.plotly_chart(corr_fig, use_container_width=True)
else:
    st.info("No screening activity data to correlate yet.")

# ── Intelligence Stats ─────────────────────────────────────────────────────────
intel_left, intel_right = st.columns(2, gap="large")

with intel_left:
    st.markdown("#### Alert Severity Breakdown")
    by_sev = pd.DataFrame(intel_stats.get("by_severity", []))
    if not by_sev.empty:
        sev_colors = {"HIGH": "#dc3545", "MEDIUM": "#e8960c", "LOW": "#0f5a85"}
        fig3 = go.Figure(go.Bar(
            x=by_sev["severity"],
            y=by_sev["count"],
            marker_color=[sev_colors.get(s, "#8899a6") for s in by_sev["severity"]],
        ))
        fig3.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            height=220, margin=dict(l=10, r=10, t=10, b=30),
            yaxis=dict(gridcolor="rgba(0,0,0,0.05)"), xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No alert data.")

with intel_right:
    st.markdown("#### Watchlist Effectiveness")
    eff = get_watchlist_effectiveness()
    if eff:
        eff_df = pd.DataFrame(eff)
        show_cols = ["keyword", "priority", "match_count", "approved", "held", "escalated"]
        available = [c for c in show_cols if c in eff_df.columns]
        st.dataframe(eff_df[available], hide_index=True, use_container_width=True)
    else:
        st.info("No watchlist items or case matches recorded yet.")

st.markdown("---")

# ── Response Time ──────────────────────────────────────────────────────────────
st.markdown("### Response Time Analysis")
rt_left, rt_right = st.columns([1.2, 0.8], gap="large")

with rt_left:
    rt_metrics = get_response_time_metrics()
    render_response_time_chart(rt_metrics)

with rt_right:
    if rt_metrics.get("overall"):
        overall = rt_metrics["overall"]
        render_metric_card("Mean Response Time", f"{overall['mean_hours']:.1f}h", f"Median {overall.get('median_hours', 0):.1f}h · P90 {overall.get('p90_hours', 0):.1f}h")
        st.caption(f"Based on {overall.get('count', 0)} resolved cases.")
    else:
        st.info("No resolved cases with response time data yet.")

# ── Recent Flagged ─────────────────────────────────────────────────────────────
st.markdown("### Recent Flagged Cases")
recent_flagged_df = pd.DataFrame(snapshot["recent_flagged"])
if recent_flagged_df.empty:
    st.info("No flagged cases currently stored.")
else:
    st.dataframe(
        recent_flagged_df[["id", "risk_level", "hazard_score", "analyst_status", "category", "submitted_at"]],
        hide_index=True,
        use_container_width=True,
    )
