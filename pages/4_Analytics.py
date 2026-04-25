from __future__ import annotations

import pandas as pd
import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.storage import analytics_snapshot
from services.sidebar import render_global_sidebar
from services.ui import apply_page_style, render_hero, render_metric_card


st.set_page_config(page_title="BioLens Analytics", layout="wide")
bootstrap_application()
apply_page_style()
render_global_sidebar()

mode = get_runtime_mode()
snapshot = analytics_snapshot()

render_hero(
    "Analytics",
    "Operational metrics sourced directly from persisted SQLite records. Use this view to summarize throughput, flagged rate, review state, and category mix.",
    mode,
)

metric_cols = st.columns(4)
with metric_cols[0]:
    render_metric_card("Total screened", str(snapshot["total"]), "All persisted cases")
with metric_cols[1]:
    render_metric_card("Flagged rate", f"{snapshot['flagged_rate']:.0%}", "REVIEW or HIGH")
with metric_cols[2]:
    render_metric_card("Open queue", str(snapshot["open_queue"]), "Cases awaiting closure")
with metric_cols[3]:
    render_metric_card("Average hazard", f"{snapshot['average_hazard_score']:.2f}", "Mean risk score")

risk_df = pd.DataFrame(snapshot["risk_distribution"])
status_df = pd.DataFrame(snapshot["status_distribution"])
activity_df = pd.DataFrame(snapshot["activity_over_time"])
category_df = pd.DataFrame(snapshot["top_categories"])
recent_flagged_df = pd.DataFrame(snapshot["recent_flagged"])

upper_left, upper_right = st.columns(2, gap="large")
with upper_left:
    st.markdown("### Risk Distribution")
    if risk_df.empty:
        st.info("No screening data available.")
    else:
        st.bar_chart(risk_df, x="risk_level", y="count")

with upper_right:
    st.markdown("### Status Distribution")
    if status_df.empty:
        st.info("No review state available yet.")
    else:
        st.bar_chart(status_df, x="analyst_status", y="count")

lower_left, lower_right = st.columns(2, gap="large")
with lower_left:
    st.markdown("### Activity Over Time")
    if activity_df.empty:
        st.info("No activity has been recorded yet.")
    else:
        activity_df["day"] = pd.to_datetime(activity_df["day"])
        st.line_chart(activity_df.set_index("day")["count"])

with lower_right:
    st.markdown("### Top Flagged Categories")
    if category_df.empty:
        st.info("No flagged categories are available yet.")
    else:
        st.bar_chart(category_df, x="category", y="count")

st.markdown("### Recent Flagged Cases")
if recent_flagged_df.empty:
    st.info("No flagged cases are currently stored.")
else:
    st.dataframe(
        recent_flagged_df[["id", "risk_level", "hazard_score", "analyst_status", "category", "submitted_at"]],
        hide_index=True,
        use_container_width=True,
    )
