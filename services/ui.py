from __future__ import annotations

import html
from datetime import datetime
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from services.constants import ACTION_STYLES, RISK_STYLES, STATUS_STYLES, RISK_COLORS, DATA_SOURCE_STYLES

def apply_page_style() -> None:
    st.markdown(
        """
<style>
            :root {
                --bl-ink: #172638;
                --bl-muted: #596979;
                --bl-panel: rgba(255, 252, 247, 0.9);
                --bl-panel-strong: rgba(248, 242, 232, 0.92);
                --bl-border: rgba(42, 71, 96, 0.14);
                --bl-accent: #0f5a85;
                --bl-accent-soft: #dff1fb;
                --bl-shadow: 0 18px 48px rgba(23, 38, 56, 0.08);
            }

            @media (prefers-color-scheme: dark) {
                :root {
                    --bl-ink: #e0e6ed;
                    --bl-muted: #8899a6;
                    --bl-panel: rgba(23, 33, 43, 0.9);
                    --bl-panel-strong: rgba(30, 42, 56, 0.92);
                    --bl-border: rgba(255, 255, 255, 0.08);
                    --bl-shadow: 0 18px 48px rgba(0, 0, 0, 0.2);
                }
            }

            html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
                background:
                    radial-gradient(circle at top left, rgba(205, 173, 122, 0.18), transparent 34%),
                    linear-gradient(180deg, #f7f0e3 0%, #edf5fb 48%, #f8fbff 100%);
                color: var(--bl-ink);
                font-family: "Avenir Next", "Trebuchet MS", sans-serif;
            }

            h1, h2, h3 {
                font-family: "Iowan Old Style", "Palatino Linotype", serif;
                letter-spacing: -0.02em;
                color: var(--bl-ink);
            }

            [data-testid="stSidebar"] {
                background:
                    linear-gradient(180deg, rgba(253, 249, 242, 0.98), rgba(239, 246, 252, 0.96));
                border-right: 1px solid var(--bl-border);
            }

            @media (prefers-color-scheme: dark) {
                html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
                    background:
                        radial-gradient(circle at top left, rgba(100, 140, 180, 0.1), transparent 34%),
                        linear-gradient(180deg, #0e141a 0%, #151e27 48%, #1a242f 100%);
                }
                [data-testid="stSidebar"] {
                    background:
                        linear-gradient(180deg, rgba(18, 26, 33, 0.98), rgba(22, 31, 41, 0.96));
                }
            }

            .block-container {
                max-width: 1180px;
                padding-top: 2rem;
                padding-bottom: 3rem;
            }

            .bl-hero {
                background:
                    linear-gradient(135deg, rgba(16, 90, 133, 0.94), rgba(31, 70, 94, 0.9)),
                    linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0));
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 28px;
                box-shadow: var(--bl-shadow);
                color: #f7fbff;
                margin-bottom: 1.4rem;
                padding: 1.75rem 2rem 1.9rem;
                position: relative;
                overflow: hidden;
            }

            .bl-hero::after {
                content: "";
                position: absolute;
                inset: auto -6% -32% auto;
                width: 240px;
                height: 240px;
                background: radial-gradient(circle, rgba(246, 211, 144, 0.38), rgba(246, 211, 144, 0));
                pointer-events: none;
            }

            .bl-eyebrow {
                color: rgba(255, 255, 255, 0.72);
                font-size: 0.78rem;
                letter-spacing: 0.16em;
                margin-bottom: 0.6rem;
                text-transform: uppercase;
            }

            .bl-hero h1 {
                color: #ffffff;
                font-size: 2.4rem;
                margin: 0 0 0.45rem 0;
            }

            .bl-hero p {
                color: rgba(247, 251, 255, 0.84);
                line-height: 1.6;
                margin: 0;
                max-width: 760px;
            }

            .bl-panel, .bl-case-card, .bl-metric-card, .bl-result-card, .bl-error-card {
                background: var(--bl-panel);
                border: 1px solid var(--bl-border);
                border-radius: 22px;
                box-shadow: var(--bl-shadow);
            }

            .bl-panel {
                padding: 1rem 1.1rem;
            }

            .bl-case-card {
                margin-bottom: 1rem;
                padding: 1.05rem 1.15rem;
            }

            .bl-case-row {
                align-items: flex-start;
                display: flex;
                gap: 1rem;
                justify-content: space-between;
                margin-bottom: 0.5rem;
            }

            .bl-case-title {
                font-family: "Iowan Old Style", "Palatino Linotype", serif;
                font-size: 1.18rem;
                font-weight: 700;
                line-height: 1.2;
            }

            .bl-case-meta, .bl-audit-text {
                color: var(--bl-muted);
                font-size: 0.92rem;
            }

            .bl-sequence-preview {
                background: rgba(20, 39, 59, 0.05);
                border-radius: 14px;
                color: #284053;
                font-family: "SFMono-Regular", Consolas, monospace;
                font-size: 0.9rem;
                margin-top: 0.7rem;
                overflow-wrap: anywhere;
                padding: 0.8rem 0.9rem;
                max-height: 250px;
                overflow-y: auto;
            }

            .bl-badge-row {
                align-items: center;
                display: flex;
                flex-wrap: wrap;
                gap: 0.45rem;
                justify-content: flex-end;
            }

            .bl-badge {
                border-radius: 999px;
                border: 1px solid transparent;
                display: inline-flex;
                font-size: 0.74rem;
                font-weight: 700;
                letter-spacing: 0.04em;
                line-height: 1;
                padding: 0.42rem 0.68rem;
                text-transform: uppercase;
            }

            .bl-metric-card {
                min-height: 132px;
                padding: 1rem 1rem 0.9rem;
            }

            .bl-metric-label {
                color: var(--bl-muted);
                font-size: 0.82rem;
                letter-spacing: 0.08em;
                margin-bottom: 0.7rem;
                text-transform: uppercase;
            }

            .bl-metric-value {
                font-family: "Iowan Old Style", "Palatino Linotype", serif;
                font-size: 1.8rem;
                font-weight: 700;
                line-height: 1.15;
                margin-bottom: 0.35rem;
            }

            .bl-metric-detail {
                color: var(--bl-muted);
                font-size: 0.92rem;
                line-height: 1.35;
            }

            .bl-audit-entry {
                margin-bottom: 0.7rem;
            }

            /* NEW COGNITIVE UI CLASSES */
            
            .bl-result-card {
                margin-bottom: 1.5rem;
                padding: 0;
                overflow: hidden;
                transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
                animation: slide-up 0.4s ease-out;
            }

            @keyframes slide-up {
                from { opacity: 0; transform: translateY(15px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .bl-result-card:hover {
                transform: translateY(-2px);
                box-shadow: 0 22px 55px rgba(23, 38, 56, 0.12);
            }

            .bl-result-card-inner {
                padding: 1.25rem 1.4rem;
                border-left: 6px solid transparent;
            }

            .bl-verdict-strip {
                display: flex;
                align-items: center;
                gap: 1.5rem;
                margin-bottom: 1rem;
                padding-bottom: 1rem;
                border-bottom: 1px solid var(--bl-border);
                flex-wrap: wrap;
            }
            
            .bl-verdict-left {
                display: flex;
                align-items: center;
                gap: 1.25rem;
            }
            
            .bl-verdict-right {
                display: flex;
                align-items: center;
                gap: 1.25rem;
                margin-left: auto;
            }

            .bl-score-gauge-container {
                position: relative;
                width: 64px;
                height: 64px;
            }

            .bl-score-gauge-text {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-family: "SFMono-Regular", Consolas, monospace;
                font-weight: 700;
                font-size: 0.9rem;
            }

            .bl-confidence-bar {
                display: flex;
                flex-direction: column;
                gap: 0.3rem;
                width: 120px;
            }
            
            .bl-confidence-label {
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--bl-muted);
                display: flex;
                justify-content: space-between;
            }

            .bl-confidence-track {
                height: 6px;
                background: rgba(0,0,0,0.06);
                border-radius: 3px;
                overflow: hidden;
            }
            
            .bl-confidence-fill {
                height: 100%;
                border-radius: 3px;
                background: var(--bl-accent);
                transition: width 1s cubic-bezier(0.22, 1, 0.36, 1);
            }

            .bl-data-source-tag {
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                font-size: 0.8rem;
                font-weight: 600;
                padding: 0.35rem 0.75rem;
                border-radius: 8px;
            }

            .bl-threat-dimension {
                display: flex;
                align-items: center;
                gap: 1rem;
                margin-bottom: 0.5rem;
            }
            
            .bl-threat-dim-label {
                width: 160px;
                font-size: 0.85rem;
                font-weight: 500;
            }
            
            .bl-threat-dim-track {
                flex: 1;
                height: 8px;
                background: rgba(0,0,0,0.04);
                border-radius: 4px;
                overflow: hidden;
            }
            
            .bl-threat-dim-fill {
                height: 100%;
                border-radius: 4px;
                background: #8899a6;
            }
            
            .bl-threat-dim-score {
                width: 40px;
                font-size: 0.8rem;
                font-family: monospace;
                text-align: right;
                color: var(--bl-muted);
            }

            .bl-attr-legend {
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.75rem;
                color: var(--bl-muted);
                margin-top: 0.5rem;
                margin-bottom: 0.2rem;
            }
            
            .bl-attr-gradient {
                height: 6px;
                width: 100px;
                border-radius: 3px;
                background: linear-gradient(90deg, rgba(231,76,60,0.1) 0%, rgba(231,76,60,0.9) 100%);
            }

            .bl-error-card {
                border-left: 4px solid #e74c3c;
                padding: 1.2rem;
                margin-bottom: 1rem;
                display: flex;
                gap: 1rem;
                align-items: flex-start;
            }
            
            .bl-error-icon {
                font-size: 1.5rem;
            }
            
            .bl-error-content h4 {
                margin: 0 0 0.4rem 0;
                color: #c0392b;
                font-size: 1.1rem;
            }
            
            .bl-error-content p {
                margin: 0;
                font-size: 0.95rem;
                color: var(--bl-ink);
            }
</style>
        """,
        unsafe_allow_html=True
    )


def _badge(text: str, background: str, foreground: str) -> str:
    return (
        f'<span class="bl-badge" style="background:{background}; color:{foreground}; border-color:{foreground}22;">'
        f"{html.escape(text)}</span>"
    )

def risk_badge(level: str | None) -> str:
    style = RISK_STYLES.get(level or "", {"bg": "#eef2f4", "fg": "#475865"})
    return _badge(level or "UNSET", style["bg"], style["fg"])


def status_badge(status: str | None) -> str:
    style = STATUS_STYLES.get(status or "", {"bg": "#eef2f4", "fg": "#475865"})
    return _badge(status or "UNSET", style["bg"], style["fg"])


def action_badge(action: str | None) -> str:
    style = ACTION_STYLES.get(action or "", {"bg": "#eef2f4", "fg": "#475865"})
    return _badge(action or "UNSET", style["bg"], style["fg"])


def render_hero(title: str, subtitle: str, mode_label: str) -> None:
    html_str = f"""
<section class="bl-hero">
<div class="bl-eyebrow">BioLens • {html.escape(mode_label.upper())} mode</div>
<h1>{html.escape(title)}</h1>
<p>{html.escape(subtitle)}</p>
</section>
"""
    st.markdown(html_str.replace("\n", " "), unsafe_allow_html=True)


def render_metric_card(label: str, value: str, detail: str) -> None:
    html_str = f"""
<div class="bl-metric-card">
<div class="bl-metric-label">{html.escape(label)}</div>
<div class="bl-metric-value">{html.escape(value)}</div>
<div class="bl-metric-detail">{html.escape(detail)}</div>
</div>
"""
    st.markdown(html_str.replace("\n", " "), unsafe_allow_html=True)


def format_timestamp(value: str | None) -> str:
    if not value:
        return "Pending"

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.astimezone().strftime("%d %b %Y, %H:%M")


def render_threat_radar(breakdown: dict[str, Any] | None, height: int = 320) -> None:
    if not breakdown:
        return
        
    categories = [
        "Pathogenicity",
        "Evasion Potential",
        "Synthesis Feasibility",
        "Env. Resilience",
        "Host Range",
    ]
    values = [
        breakdown.get("pathogenicity", 0),
        breakdown.get("evasion_potential", 0),
        breakdown.get("synthesis_feasibility", 0),
        breakdown.get("environmental_resilience", 0),
        breakdown.get("host_range", 0),
    ]
    
    # Close the polygon
    categories = [*categories, categories[0]]
    values = [*values, values[0]]
    
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        line=dict(color='#e74c3c' if sum(values) > 2.5 else '#0f5a85'),
        fillcolor='rgba(231, 76, 60, 0.2)' if sum(values) > 2.5 else 'rgba(15, 90, 133, 0.2)',
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1]),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
        height=height,
    )
    st.plotly_chart(fig)


def render_attributed_sequence(sequence: str, attribution_data: dict[str, Any] | None) -> None:
    if not attribution_data or not attribution_data.get("positions"):
        st.code(sequence, language="text", wrap_lines=True)
        return

    positions = set(attribution_data.get("positions", []))
    scores = attribution_data.get("scores", [])
    pos_to_score = dict(zip(attribution_data.get("positions", []), scores))

    st.markdown(
        '''
<div class="bl-attr-legend">
<span>Low Risk</span>
<div class="bl-attr-gradient"></div>
<span>High Risk</span>
</div>
        ''', unsafe_allow_html=True
    )

    html_parts = ['<div class="bl-sequence-preview" style="line-height: 1.6; word-break: break-all; font-family: monospace;">']
    
    for i, char in enumerate(sequence):
        if i in positions:
            score = pos_to_score.get(i, 0)
            # Yellow to red highlight based on score
            intensity = min(score, 1.0)
            # Use hsla for a yellow-to-red gradient (60 hue is yellow, 0 is red)
            hue = 60 * (1 - intensity)
            bg_color = f"hsla({hue}, 90%, 65%, {0.2 + intensity*0.8})"
            html_parts.append(f'<span style="background-color: {bg_color}; border-radius: 2px; padding: 0 1px; font-weight: 600;" title="Attribution: {score:.2f}">{char}</span>')
        else:
            html_parts.append(f'<span style="opacity: 0.8;">{char}</span>')
            
    html_parts.append('</div>')
    st.markdown("".join(html_parts), unsafe_allow_html=True)
    
    regions = attribution_data.get("regions", [])
    if regions:
        st.markdown("<div style='margin-top: 0.5rem; font-size: 0.85rem; color: var(--bl-muted);'><strong>Highlighted Regions:</strong></div>", unsafe_allow_html=True)
        for r in regions:
            st.markdown(f"<div style='font-size: 0.8rem; margin-top: 0.2rem;'>• {r['label']} (Pos {r['start']}-{r['end']}, Score {r['score']:.2f})</div>", unsafe_allow_html=True)

# --- NEW UI COMPONENTS ---

def render_score_gauge(score: float, risk_level: str) -> str:
    color = RISK_COLORS.get(risk_level, "#475865")
    circumference = 2 * 3.14159 * 28
    offset = circumference - (score * circumference)
    
    return f"""
<div class="bl-score-gauge-container">
<svg width="64" height="64" viewBox="0 0 64 64">
<circle cx="32" cy="32" r="28" fill="none" stroke="rgba(0,0,0,0.06)" stroke-width="6" />
<circle cx="32" cy="32" r="28" fill="none" stroke="{color}" stroke-width="6" 
                stroke-dasharray="{circumference}" stroke-dashoffset="{offset}" 
                transform="rotate(-90 32 32)" stroke-linecap="round" 
                style="transition: stroke-dashoffset 1s ease-out;" />
</svg>
<div class="bl-score-gauge-text" style="color: {color};">{score:.2f}</div>
</div>
    """

def render_confidence_bar(confidence: float) -> str:
    pct = int(confidence * 100)
    color = "#1f6a4d" if pct > 70 else ("#8a4c00" if pct > 40 else "#8f2424")
    return f"""
<div class="bl-confidence-bar">
<div class="bl-confidence-label">
<span>Confidence</span>
<span style="color: {color}; font-weight: 600;">{pct}%</span>
</div>
<div class="bl-confidence-track">
<div class="bl-confidence-fill" style="width: {pct}%; background: {color};"></div>
</div>
</div>
    """

def render_data_source_tag(data_source: str | None) -> str:
    ds = data_source or "unknown"
    style = DATA_SOURCE_STYLES.get(ds, {"bg": "#eef2f4", "fg": "#475865", "label": ds})
    return f"""
<div class="bl-data-source-tag" style="background: {style['bg']}; color: {style['fg']}; border: 1px solid {style['fg']}33;">
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
</svg>
        {style['label']}
</div>
    """

def render_verdict_strip(result: dict[str, Any]) -> str:
    score_gauge = render_score_gauge(result["hazard_score"], result["risk_level"])
    badge = risk_badge(result["risk_level"])
    confidence_bar = render_confidence_bar(result["confidence"])
    data_source = render_data_source_tag(result.get("data_source"))
    
    return f"""
<div class="bl-verdict-strip">
<div class="bl-verdict-left">
{score_gauge}
{badge}
</div>
<div class="bl-verdict-right">
{confidence_bar}
{data_source}
</div>
</div>
    """

def render_threat_bars(breakdown: dict[str, Any] | None) -> None:
    if not breakdown:
        st.info("No structured threat breakdown available.")
        return
        
    metrics = [
        ("Pathogenicity", breakdown.get("pathogenicity", 0)),
        ("Evasion Potential", breakdown.get("evasion_potential", 0)),
        ("Synthesis Feasibility", breakdown.get("synthesis_feasibility", 0)),
        ("Env. Resilience", breakdown.get("environmental_resilience", 0)),
        ("Host Range", breakdown.get("host_range", 0)),
    ]
    
    html_parts = []
    for label, score in metrics:
        color = "#e74c3c" if score > 0.6 else ("#f39c12" if score > 0.3 else "#2ecc71")
        pct = score * 100
        html_parts.append(f"""
<div class="bl-threat-dimension">
<div class="bl-threat-dim-label">{label}</div>
<div class="bl-threat-dim-track">
<div class="bl-threat-dim-fill" style="width: {pct}%; background: {color};"></div>
</div>
<div class="bl-threat-dim-score">{score:.2f}</div>
</div>
        """)
        
    st.markdown("".join(html_parts), unsafe_allow_html=True)

def render_error_card(title: str, detail: str) -> None:
    html_str = f"""
<div class="bl-error-card">
<div class="bl-error-icon">⚠️</div>
<div class="bl-error-content">
<h4>{html.escape(title)}</h4>
<p>{html.escape(detail)}</p>
</div>
</div>
"""
    st.markdown(html_str.replace("\n", " "), unsafe_allow_html=True)


def render_primary_risk_drivers(breakdown: dict[str, Any] | None) -> None:
    if not breakdown:
        st.info("No structured threat breakdown available.")
        return

    sorted_dims = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
    top_dims = sorted_dims[:2]
    
    dim_labels = {
        "pathogenicity": "Pathogenicity",
        "evasion_potential": "Evasion Potential",
        "synthesis_feasibility": "Synthesis Feasibility",
        "environmental_resilience": "Env. Resilience",
        "host_range": "Host Range"
    }
    
    dim_explanations = {
        "pathogenicity": "Sequence contains motifs highly associated with toxin production or virulence.",
        "evasion_potential": "Features indicate structural or regulatory mechanisms to bypass host immunity.",
        "synthesis_feasibility": "High feasibility indicates the sequence can be easily ordered via standard commercial synthesis pipelines.",
        "environmental_resilience": "Sequence demonstrates robust stability in external environments.",
        "host_range": "Broad compatibility suggests the ability to infect or affect multiple host species."
    }
    
    html_parts = ['<div style="display: flex; flex-direction: column; gap: 0.8rem;">']
    
    for dim_key, score in top_dims:
        if score > 0.6:
            icon = "🔴"
            color = "#dc3545"
        elif score > 0.3:
            icon = "🟠"
            color = "#e8960c"
        else:
            icon = "🟢"
            color = "#198754"
            
        label = dim_labels.get(dim_key, dim_key)
        explanation = dim_explanations.get(dim_key, "Elevated signal detected in this dimension.")
        
        html_parts.append(f"""<div style="background: rgba(255,255,255,0.4); border: 1px solid var(--bl-border); border-radius: 8px; padding: 0.8rem; font-size: 0.9rem; margin-bottom: 0.8rem;">
<div style="font-weight: 600; color: {color}; margin-bottom: 0.3rem; display: flex; align-items: center; gap: 0.4rem;">
{icon} {label} ({score:.2f})
</div>
<div style="color: var(--bl-ink); line-height: 1.4;">
{explanation}
</div>
</div>""")
        
    html_parts.append('</div>')
    st.markdown("".join(html_parts), unsafe_allow_html=True)
