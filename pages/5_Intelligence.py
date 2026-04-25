from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from services.ui import apply_page_style

st.set_page_config(page_title="BioLens - Intelligence", layout="wide")
apply_page_style()

st.title("Threat Intelligence")
st.markdown("Live policy updates and emerging biosecurity alerts.")

def load_intel_feed() -> list[dict]:
    feed_path = Path("data/intel_feed.json")
    if feed_path.exists():
        with open(feed_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

feed_data = load_intel_feed()

if not feed_data:
    st.info("No intelligence feed data found. Please ensure data/intel_feed.json exists.")
else:
    # Separate into categories
    policies = [item for item in feed_data if item.get("category") == "policy"]
    alerts = [item for item in feed_data if item.get("category") == "alert"]
    research = [item for item in feed_data if item.get("category") == "research"]

    st.markdown("### Active Policies & Regulations")
    st.markdown("These guidelines shape the current triage thresholds for Synthscreen results.")
    
    policy_cols = st.columns(3)
    for i, p in enumerate(policies):
        col = policy_cols[i % 3]
        with col:
            st.markdown(
                f"""
<div class="bl-panel" style="margin-bottom: 1rem;">
<div style="font-size: 0.8rem; color: var(--bl-muted); text-transform: uppercase; margin-bottom: 0.3rem;">{p['date']} • {p['source']}</div>
<div style="font-weight: 600; font-size: 1.05rem; margin-bottom: 0.5rem; line-height: 1.3;">{p['title']}</div>
<div style="font-size: 0.9rem; margin-bottom: 0.8rem;">{p['summary']}</div>
<div style="background: rgba(15, 90, 133, 0.08); padding: 0.6rem; border-radius: 6px; font-size: 0.85rem; border-left: 3px solid var(--bl-accent);">
<strong>Workflow Impact:</strong> {p['relevance_to_screening']}
</div>
</div>
                """,
                unsafe_allow_html=True
            )

    st.markdown("---")
    
    col_left, col_right = st.columns(2, gap="large")
    
    with col_left:
        st.markdown("### Emerging Alerts")
        if not alerts:
            st.markdown("<p style='color: var(--bl-muted);'>No active alerts.</p>", unsafe_allow_html=True)
        for a in alerts:
            st.markdown(
                f"""
<div class="bl-case-card" style="border-left: 4px solid #e74c3c;">
<div class="bl-case-row">
<div>
<div class="bl-case-title" style="color: #c0392b;">{a['title']}</div>
<div class="bl-case-meta">{a['date']} • {a['source']}</div>
</div>
</div>
<div style="font-size: 0.95rem; margin-top: 0.4rem; margin-bottom: 0.8rem;">{a['summary']}</div>
<div style="font-size: 0.85rem; color: var(--bl-muted);"><strong>Note:</strong> {a['relevance_to_screening']}</div>
</div>
                """,
                unsafe_allow_html=True
            )

    with col_right:
        st.markdown("### Screening Research & Insights")
        if not research:
            st.markdown("<p style='color: var(--bl-muted);'>No recent research publications.</p>", unsafe_allow_html=True)
        for r in research:
            st.markdown(
                f"""
<div class="bl-case-card" style="border-left: 4px solid #3498db;">
<div class="bl-case-row">
<div>
<div class="bl-case-title" style="color: #2980b9;">{r['title']}</div>
<div class="bl-case-meta">{r['date']} • {r['source']}</div>
</div>
</div>
<div style="font-size: 0.95rem; margin-top: 0.4rem; margin-bottom: 0.8rem;">{r['summary']}</div>
<div style="font-size: 0.85rem; color: var(--bl-muted);"><strong>Insight:</strong> {r['relevance_to_screening']}</div>
</div>
                """,
                unsafe_allow_html=True
            )
