from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services.constants import (
    ALERT_SEVERITIES,
    ALERT_SIGNAL_TYPES,
    ALERT_SOURCE_TYPES,
)
from services.intelligence import (
    add_to_watchlist,
    create_manual_alert,
    ensure_demo_alerts,
    get_alert_statistics,
    get_alert_timeline,
    get_watchlist_effectiveness,
    import_alerts_from_json,
    list_alerts,
    list_watchlist,
    remove_from_watchlist,
    update_alert_status,
)
from services.sidebar import render_global_sidebar
from services.ui import apply_page_style, render_alert_card

st.set_page_config(page_title="BioLens — Intelligence", layout="wide")
apply_page_style()
render_global_sidebar()

ensure_demo_alerts()

st.title("Early-Warning Intelligence")
st.markdown(
    "Monitor outbreak, surveillance, policy, and research signals. "
    "Add signals to the watchlist to automatically flag relevant sequences at screening time."
)

alerts = list_alerts()
active_watchlist = list_watchlist(active_only=True)
stats = get_alert_statistics()

# ── Metrics ────────────────────────────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.markdown(f"**Active Alerts:** {len([a for a in alerts if a['status'] not in ('DISMISSED', 'REVIEWED')])}")
with m2:
    st.markdown(f"**HIGH Severity:** {len([a for a in alerts if a['severity'] == 'HIGH'])}")
with m3:
    st.markdown(f"**Watchlisted:** {len(active_watchlist)}")
with m4:
    st.markdown(f"**Reviewed:** {len([a for a in alerts if a['status'] == 'REVIEWED'])}")
with m5:
    st.markdown(f"**Case Links:** {stats.get('total_case_links', 0)}")

st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs(["📡 Alert Feed", "🎯 Active Watchlist", "➕ Create / Import Alerts", "📈 Signal Timeline"])

# ── Tab 1: Alert Feed ──────────────────────────────────────────────────────────
with tab1:
    filter_cols = st.columns(4)
    with filter_cols[0]:
        f_severity = st.selectbox("Severity", ["All", "HIGH", "MEDIUM", "LOW"], key="f_sev")
    with filter_cols[1]:
        f_signal = st.selectbox(
            "Signal Type",
            ["All", "OUTBREAK_SIGNAL", "SURVEILLANCE_ANOMALY", "POLICY_UPDATE", "RESEARCH_SIGNAL", "SCREENING_RELEVANCE"],
            key="f_sig",
        )
    with filter_cols[2]:
        regions = ["All Regions"] + sorted(list(set(a["region"] for a in alerts)))
        f_region = st.selectbox("Region", regions, key="f_reg")
    with filter_cols[3]:
        f_status = st.selectbox("Status", ["NEW", "REVIEWED", "WATCHLISTED", "DISMISSED", "All"], key="f_sta")

    filtered_alerts = list_alerts(
        status=None if f_status == "All" else f_status,
        severity=None if f_severity == "All" else f_severity,
        signal_type=None if f_signal == "All" else f_signal,
        region=None if f_region == "All Regions" else f_region,
    )

    if not filtered_alerts:
        st.info("No alerts match your filters.")

    for alert in filtered_alerts:
        with st.container():
            render_alert_card(alert)

            action_cols = st.columns([1, 1, 1, 4])

            if alert["status"] == "NEW":
                with action_cols[0]:
                    if st.button("✓ Reviewed", key=f"rev_{alert['id']}"):
                        update_alert_status(alert["id"], "REVIEWED")
                        st.rerun()
                with action_cols[1]:
                    if st.button("➕ Watchlist", key=f"watch_{alert['id']}"):
                        st.session_state[f"watching_{alert['id']}"] = True
                        st.rerun()
                with action_cols[2]:
                    if st.button("✕ Dismiss", key=f"dis_{alert['id']}"):
                        update_alert_status(alert["id"], "DISMISSED")
                        st.rerun()

            # Inline watchlist form
            if st.session_state.get(f"watching_{alert['id']}"):
                with st.form(f"form_watch_{alert['id']}"):
                    st.write(f"Add **{alert['title']}** to Watchlist")
                    suggested_kw = alert.get("suggested_action", "").split()[-1] if alert.get("suggested_action") else "context"
                    w_kw = st.text_input("Match Keyword(s)", value=suggested_kw)
                    w_cat = st.text_input("Match Category", value="intelligence_context")
                    if st.form_submit_button("Confirm Add to Watchlist"):
                        add_to_watchlist(alert["id"], w_kw, w_cat, alert["region"])
                        del st.session_state[f"watching_{alert['id']}"]
                        st.success("Added to watchlist!")
                        st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)


# ── Tab 2: Active Watchlist ────────────────────────────────────────────────────
with tab2:
    if not active_watchlist:
        st.info("Watchlist is empty. Add signals from the Alert Feed.")
    else:
        effectiveness = get_watchlist_effectiveness()
        eff_by_id = {row["id"]: row for row in effectiveness}

        for item in active_watchlist:
            eff = eff_by_id.get(item["id"], {})
            match_count = eff.get("match_count", 0)
            approved = eff.get("approved", 0)
            held = eff.get("held", 0)
            escalated = eff.get("escalated", 0)

            st.markdown(
                f"""
<div style="background: var(--bl-panel); border: 1px solid var(--bl-border); border-radius: 8px;
            padding: 1rem; margin-bottom: 1rem; border-left: 4px solid var(--bl-accent);">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
        <strong style="font-size: 1.05rem;">🔍 {item['keyword']}</strong>
        <span style="background: rgba(15,90,133,0.1); padding: 0.2rem 0.6rem; border-radius: 4px;
                     font-size: 0.8rem; font-weight: bold; color: var(--bl-accent);">Priority: {item['priority']}</span>
    </div>
    <div style="font-size: 0.88rem; color: var(--bl-muted); margin-bottom: 0.3rem;">
        Category: {item['category']} &nbsp;|&nbsp; Region: {item['region']}
    </div>
    <div style="font-size: 0.88rem; margin-bottom: 0.6rem;">{item['reason']}</div>
    <div style="font-size: 0.82rem; color: var(--bl-muted);">
        Case matches: <strong>{match_count}</strong> &nbsp;·&nbsp;
        Approved: {approved} &nbsp;·&nbsp;
        Held: {held} &nbsp;·&nbsp;
        Escalated: {escalated}
    </div>
</div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Remove from Watchlist", key=f"rm_watch_{item['id']}"):
                remove_from_watchlist(item["id"])
                st.rerun()


# ── Tab 3: Create / Import Alerts ─────────────────────────────────────────────
with tab3:
    create_col, import_col = st.columns([1.1, 0.9], gap="large")

    with create_col:
        st.markdown("#### ✍️ Create Manual Alert")
        with st.form("create_alert_form"):
            c_title = st.text_input("Title *", placeholder="Brief descriptive title")
            c_summary = st.text_area("Summary *", height=100, placeholder="What happened? Why does it matter?")
            c1, c2 = st.columns(2)
            with c1:
                c_source_type = st.selectbox("Source Type", list(ALERT_SOURCE_TYPES))
                c_signal_type = st.selectbox("Signal Type", list(ALERT_SIGNAL_TYPES))
                c_severity = st.selectbox("Severity", ["HIGH", "MEDIUM", "LOW"])
            with c2:
                c_source_name = st.text_input("Source Name *", placeholder="e.g. WHO, ProMED, Internal")
                c_region = st.text_input("Region *", value="Global")
                c_confidence = st.slider("Confidence (%)", 0, 100, 75)
            c_screening_relevance = st.text_input(
                "Screening Relevance",
                placeholder="How does this affect what analysts should screen for?",
            )
            c_suggested_action = st.text_input(
                "Suggested Action",
                placeholder="e.g. Add to watchlist, Mark reviewed",
            )
            submitted = st.form_submit_button("Create Alert", type="primary", use_container_width=True)

        if submitted:
            if not c_title.strip() or not c_summary.strip() or not c_source_name.strip() or not c_region.strip():
                st.error("Title, Summary, Source Name, and Region are required.")
            else:
                try:
                    alert_id = create_manual_alert(
                        title=c_title,
                        summary=c_summary,
                        source_type=c_source_type,
                        source_name=c_source_name,
                        region=c_region,
                        signal_type=c_signal_type,
                        severity=c_severity,
                        confidence=c_confidence,
                        screening_relevance=c_screening_relevance,
                        suggested_action=c_suggested_action,
                    )
                    st.success(f"✅ Alert created: `{alert_id[:8]}`")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    with import_col:
        st.markdown("#### 📥 Import Alerts from JSON")
        st.caption(
            "Upload a JSON file containing an array of alert objects. "
            "Required field: `title`. All other fields are optional with sensible defaults."
        )

        uploaded = st.file_uploader("Upload JSON", type=["json"], key="alert_import_upload")
        if uploaded is not None:
            try:
                raw = uploaded.getvalue().decode("utf-8")
                result = import_alerts_from_json(raw)
                st.success(
                    f"✅ Import complete: {result['inserted']} inserted, "
                    f"{result['skipped']} skipped (of {result['total']} total)."
                )
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

        st.markdown("---")
        st.markdown("**JSON Format**")
        st.code(
            json.dumps([{
                "title": "Example Alert",
                "summary": "Brief description of the signal.",
                "source_type": "PUBLIC_HEALTH",
                "source_name": "WHO",
                "region": "Global",
                "signal_type": "OUTBREAK_SIGNAL",
                "severity": "HIGH",
                "confidence": 85,
                "screening_relevance": "How this affects screening.",
                "suggested_action": "Add to watchlist.",
            }], indent=2),
            language="json",
        )


# ── Tab 4: Signal Timeline ─────────────────────────────────────────────────────
with tab4:
    timeline = get_alert_timeline()

    if not timeline:
        st.info("No alert history to visualise yet.")
    else:
        df = pd.DataFrame(timeline)
        df["day"] = pd.to_datetime(df["day"])

        tl_col1, tl_col2 = st.columns([1.6, 1.0], gap="large")

        with tl_col1:
            st.markdown("#### Alert Volume Over Time")
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df["day"],
                y=df["count"],
                name="Total Alerts",
                marker_color="rgba(15, 90, 133, 0.7)",
            ))
            fig.add_trace(go.Bar(
                x=df["day"],
                y=df["high_count"],
                name="HIGH Severity",
                marker_color="rgba(220, 53, 69, 0.8)",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                barmode="overlay",
                height=300,
                margin=dict(l=10, r=10, t=10, b=30),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(showgrid=False),
                yaxis=dict(gridcolor="rgba(0,0,0,0.05)"),
            )
            st.plotly_chart(fig, use_container_width=True)

        with tl_col2:
            st.markdown("#### Signal Type Breakdown")
            by_type = pd.DataFrame(stats.get("by_signal_type", []))
            if not by_type.empty:
                fig2 = go.Figure(go.Pie(
                    labels=by_type["signal_type"],
                    values=by_type["count"],
                    hole=0.4,
                    textinfo="label+percent",
                    marker=dict(colors=["#0f5a85", "#e8960c", "#198754", "#dc3545", "#8a4c00"]),
                ))
                fig2.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                    height=300,
                    margin=dict(l=5, r=5, t=5, b=5),
                )
                st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Regional Distribution")
        by_region = pd.DataFrame(stats.get("by_region", []))
        if not by_region.empty:
            st.dataframe(
                by_region.rename(columns={"region": "Region", "count": "Alerts", "max_severity": "Max Severity"}),
                hide_index=True,
                use_container_width=True,
            )

        st.markdown("#### Watchlist Effectiveness")
        eff_df = pd.DataFrame(get_watchlist_effectiveness())
        if not eff_df.empty:
            display_cols = ["keyword", "category", "priority", "match_count", "approved", "held", "escalated"]
            available = [c for c in display_cols if c in eff_df.columns]
            st.dataframe(eff_df[available], hide_index=True, use_container_width=True)
        else:
            st.info("No watchlist effectiveness data yet — add watchlist items and screen some sequences.")
