from __future__ import annotations

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.automation import (
    create_rule,
    delete_rule,
    get_automation_log,
    list_rules,
    seed_default_rules,
    toggle_rule,
)
from services.constants import ANALYST_STATUSES, AUTOMATION_ACTIONS
from services.sidebar import render_global_sidebar
from services.ui import apply_page_style, render_hero, render_metric_card


st.set_page_config(page_title="BioLens — Automation", layout="wide")
bootstrap_application()
apply_page_style()
render_global_sidebar()

mode = get_runtime_mode()
current_role = st.session_state.get("user_role", "Analyst")

render_hero(
    "Automation Rules",
    "Define rules that automatically escalate or flag cases when intelligence watchlist matches meet defined priority and severity thresholds.",
    mode,
)

# Seed default rules on first visit
seed_default_rules()

# Supervisor-only warning for analysts
if current_role != "Supervisor":
    st.warning("⚠️ Automation rule management requires **Supervisor** access. Switch roles in the sidebar to manage rules.")

rules = list_rules()
log = get_automation_log(limit=50)

# ── Metrics ────────────────────────────────────────────────────────────────────
m1, m2, m3 = st.columns(3)
with m1:
    render_metric_card("Total Rules", str(len(rules)), f"{sum(1 for r in rules if r.enabled)} enabled")
with m2:
    render_metric_card("Total Firings", str(sum(r.fire_count for r in rules)), "All-time rule activations")
with m3:
    render_metric_card("Recent Firings", str(len(log)), "Last 50 automation events")

st.markdown("---")

tab1, tab2, tab3 = st.tabs(["📋 Active Rules", "➕ Create Rule", "📜 Activity Log"])

# ── Tab 1: Active Rules ────────────────────────────────────────────────────────
with tab1:
    if not rules:
        st.info("No automation rules defined yet. Use the Create Rule tab to get started.")
    else:
        for rule in rules:
            with st.container():
                col_info, col_actions = st.columns([1.0, 0.3], gap="medium")
                with col_info:
                    status_icon = "🟢" if rule.enabled else "⚫"
                    st.markdown(
                        f"""
<div style="background: var(--bl-panel); border: 1px solid var(--bl-border); border-radius: 10px;
            padding: 0.9rem 1.1rem; margin-bottom: 0.5rem;
            border-left: 4px solid {'#198754' if rule.enabled else '#8899a6'};">
    <div style="font-size: 1rem; font-weight: 600; margin-bottom: 0.3rem;">
        {status_icon} {rule.name}
    </div>
    <div style="font-size: 0.85rem; color: var(--bl-muted); margin-bottom: 0.5rem;">{rule.description}</div>
    <div style="font-size: 0.82rem; display: flex; gap: 1.5rem; flex-wrap: wrap;">
        <span>Trigger: <strong>{rule.trigger_priority}</strong> priority match + <strong>{rule.trigger_severity}</strong> severity alert</span>
        <span>Action: <strong>{rule.action}</strong> → Status: <strong>{rule.target_status}</strong></span>
        <span>Fired: <strong>{rule.fire_count}</strong>×</span>
    </div>
</div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_actions:
                    if current_role == "Supervisor":
                        toggle_label = "Disable" if rule.enabled else "Enable"
                        if st.button(toggle_label, key=f"toggle_{rule.id}", use_container_width=True):
                            toggle_rule(rule.id, not rule.enabled)
                            st.rerun()
                        if st.button("Delete", key=f"del_{rule.id}", use_container_width=True, type="secondary"):
                            delete_rule(rule.id)
                            st.rerun()


# ── Tab 2: Create Rule ─────────────────────────────────────────────────────────
with tab2:
    if current_role != "Supervisor":
        st.info("Supervisor access required to create automation rules.")
    else:
        with st.form("create_rule_form"):
            r_name = st.text_input("Rule Name *", placeholder="e.g. Auto-Escalate HIGH outbreak matches")
            r_desc = st.text_area("Description", height=80, placeholder="Describe when this rule fires and why.")

            c1, c2 = st.columns(2)
            with c1:
                r_trigger_priority = st.selectbox(
                    "Minimum Watchlist Match Priority",
                    ["HIGH", "MEDIUM", "LOW"],
                    help="Rule fires when a match with this priority OR HIGHER is found.",
                )
                r_trigger_severity = st.selectbox(
                    "Minimum Alert Severity",
                    ["HIGH", "MEDIUM", "LOW"],
                    help="Rule fires when the linked alert has this severity OR HIGHER.",
                )
            with c2:
                r_action = st.selectbox(
                    "Action",
                    list(AUTOMATION_ACTIONS),
                    help="What BioLens should do when the rule fires.",
                )
                r_target_status = st.selectbox(
                    "Set Analyst Status To",
                    [s for s in ANALYST_STATUSES if s not in ("CLEARED", "CLOSED")],
                    index=2,  # default ESCALATED
                    help="The analyst_status to assign to the matched case.",
                )

            submitted = st.form_submit_button("Create Rule", type="primary", use_container_width=True)

        if submitted:
            if not r_name.strip():
                st.error("Rule Name is required.")
            else:
                try:
                    new_rule = create_rule(
                        name=r_name,
                        description=r_desc,
                        trigger_priority=r_trigger_priority,
                        trigger_severity=r_trigger_severity,
                        action=r_action,
                        target_status=r_target_status,
                        created_by=current_role,
                    )
                    st.success(f"✅ Rule created: **{new_rule.name}**")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


# ── Tab 3: Activity Log ────────────────────────────────────────────────────────
with tab3:
    if not log:
        st.info("No automation events recorded yet. Rules fire when sequences are screened and saved to the inbox.")
    else:
        for entry in log:
            st.markdown(
                f"""
<div style="display: flex; gap: 1rem; align-items: flex-start; padding: 0.6rem 0;
            border-bottom: 1px solid var(--bl-border); font-size: 0.88rem;">
    <div style="font-size: 1.2rem; flex-shrink:0;">⚡</div>
    <div style="flex: 1;">
        <div style="font-weight: 600; margin-bottom: 0.2rem;">{entry['rule_name']}</div>
        <div style="color: var(--bl-muted); margin-bottom: 0.2rem;">{entry['match_reason']}</div>
        <div style="color: var(--bl-muted);">
            Case <code>{entry['case_id'][:8]}</code> &nbsp;·&nbsp;
            Action: <strong>{entry['action_taken']}</strong> &nbsp;·&nbsp;
            {entry['fired_at'][:16].replace('T', ' ')}
        </div>
    </div>
</div>
                """,
                unsafe_allow_html=True,
            )
