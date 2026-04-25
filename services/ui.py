from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from services.constants import ACTION_STYLES, RISK_STYLES, STATUS_STYLES, RISK_COLORS, DATA_SOURCE_STYLES

_DARK_CSS = """<style>
:root {
    --bl-ink: #dce6f0 !important;
    --bl-muted: #8899a6 !important;
    --bl-panel: rgba(20, 30, 44, 0.94) !important;
    --bl-panel-strong: rgba(26, 38, 54, 0.95) !important;
    --bl-border: rgba(255, 255, 255, 0.09) !important;
    --bl-accent: #4da6d8 !important;
    --bl-accent-soft: rgba(77, 166, 216, 0.14) !important;
    --bl-shadow: 0 18px 48px rgba(0, 0, 0, 0.30) !important;
}
html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"], [data-testid="stApp"] {
    background:
        radial-gradient(circle at top left, rgba(60,100,140,0.10), transparent 34%),
        linear-gradient(180deg, #0c1520 0%, #101928 48%, #131f2d 100%) !important;
    color: #dce6f0 !important;
}
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(11,17,27,0.99), rgba(14,22,34,0.98)) !important;
    border-right: 1px solid rgba(255,255,255,0.07) !important;
}
.block-container { background: transparent !important; }
.bl-sequence-preview { background: rgba(255,255,255,0.05) !important; color: #a0b4c6 !important; }
.bl-mode-chip {
    background: rgba(18,28,44,0.97) !important;
    border-color: rgba(255,255,255,0.13) !important;
    color: #4da6d8 !important;
}
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input {
    background-color: rgba(255,255,255,0.06) !important;
    color: #dce6f0 !important;
    border-color: rgba(255,255,255,0.12) !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder { color: rgba(220,230,240,0.35) !important; }
[data-baseweb="select"] { background-color: rgba(255,255,255,0.06) !important; }
[data-testid="stForm"] { border-color: rgba(255,255,255,0.09) !important; }
details[data-testid="stExpander"] {
    border-color: rgba(255,255,255,0.09) !important;
    background: rgba(20,30,44,0.5) !important;
}
[data-testid="stCaption"] p { color: #8899a6 !important; }
[data-testid="stMarkdownContainer"] p { color: #dce6f0 !important; }
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 { color: #eef4fa !important; }
[data-testid="stRadio"] p, [data-testid="stCheckbox"] p { color: #c8d8e8 !important; }
[data-testid="baseButton-secondary"], [data-testid="baseButton-tertiary"] {
    background: rgba(255,255,255,0.08) !important;
    color: #dce6f0 !important;
    border-color: rgba(255,255,255,0.14) !important;
}
</style>"""


def chart_font_color() -> str:
    return "#c0d0e0"


def _inject_theme_css() -> None:
    st.markdown(_DARK_CSS, unsafe_allow_html=True)


def render_mode_chip() -> None:
    """Handle UI mode query param from chip clicks and render the floating mode chip."""
    from services import get_ui_mode

    qp_mode = st.query_params.get("ui_mode")
    if qp_mode in ("compact", "full"):
        os.environ["BIOLENS_UI_MODE"] = qp_mode
        del st.query_params["ui_mode"]
        st.rerun()

    ui_mode = get_ui_mode()
    next_mode = "full" if ui_mode == "compact" else "compact"
    chip_label = "Compact" if ui_mode == "compact" else "Full"

    st.markdown(
        f'<a href="?ui_mode={next_mode}" class="bl-mode-chip" title="Switch to {next_mode} view">{chip_label}</a>',
        unsafe_allow_html=True,
    )


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

            /* Dark mode overrides */
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
                .bl-sequence-preview {
                    background: rgba(255, 255, 255, 0.05);
                    color: #b0c0cc;
                }
            }

            .block-container {
                max-width: 1180px;
                padding-top: 2rem;
                padding-bottom: 3rem;
            }

            .bl-hero {
                background: linear-gradient(135deg, #0a1c30 0%, #0e3554 55%, #113f65 100%);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 22px;
                box-shadow: 0 20px 56px rgba(10, 28, 48, 0.26);
                color: #eef5fc;
                margin: 0 0.5rem 1.4rem;
                padding: 2.6rem 2.4rem 2.9rem;
                position: relative;
                overflow: hidden;
            }

            .bl-hero::after {
                display: none;
            }

            .bl-eyebrow {
                color: rgba(255, 255, 255, 0.72);
                font-size: 0.78rem;
                letter-spacing: 0.16em;
                margin-bottom: 0.6rem;
                text-transform: uppercase;
            }

            .bl-hero h1 {
                color: #f0f8ff;
                font-size: 2.4rem;
                margin: 0 0 0.5rem 0;
                letter-spacing: -0.025em;
            }

            .bl-hero p {
                color: rgba(224, 240, 255, 0.82);
                line-height: 1.65;
                margin: 0;
                max-width: 740px;
                font-size: 1.01rem;
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
                cursor: pointer;
                margin-bottom: 1rem;
                padding: 1.05rem 1.15rem;
                transition: box-shadow 0.15s, transform 0.15s;
            }

            .bl-case-card:hover {
                box-shadow: 0 22px 55px rgba(23, 38, 56, 0.12);
                transform: translateY(-1px);
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

            @media (prefers-color-scheme: dark) {
                .bl-sequence-preview {
                    background: rgba(255, 255, 255, 0.05);
                    color: #b0c0cc;
                }
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

            /* Hide Streamlit auto-generated sidebar nav — replaced by custom nav */
            [data-testid="stSidebarNav"] { display: none !important; }

            /* Compact/Full mode floating chip */
            .bl-mode-chip {
                position: fixed;
                top: 0.55rem;
                right: 1.2rem;
                z-index: 1000;
                background: rgba(255, 252, 247, 0.96);
                border: 1px solid rgba(42, 71, 96, 0.22);
                border-radius: 999px;
                padding: 0.28rem 0.85rem;
                font-size: 0.76rem;
                font-weight: 700;
                letter-spacing: 0.04em;
                box-shadow: 0 2px 10px rgba(23, 38, 56, 0.14);
                cursor: pointer;
                text-decoration: none !important;
                color: var(--bl-accent) !important;
                transition: box-shadow 0.15s;
            }

            .bl-mode-chip:hover {
                box-shadow: 0 4px 18px rgba(23, 38, 56, 0.2);
                text-decoration: none !important;
            }

            @media (prefers-color-scheme: dark) {
                .bl-mode-chip {
                    background: rgba(23, 33, 43, 0.96);
                    border-color: rgba(255, 255, 255, 0.15);
                    color: #5ab4e0 !important;
                }
            }
</style>
        """,
        unsafe_allow_html=True
    )
    _inject_theme_css()
    render_mode_chip()


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

def severity_badge(severity: str | None) -> str:
    from services.constants import SEVERITY_STYLES
    style = SEVERITY_STYLES.get(severity or "", {"bg": "#eef2f4", "fg": "#475865"})
    return _badge(severity or "UNSET", style["bg"], style["fg"])

def signal_type_badge(signal_type: str | None) -> str:
    # Generic style for signal types
    return _badge(signal_type or "UNKNOWN", "#eef2f4", "#475865")


def render_hero(title: str, subtitle: str, mode_label: str, compact: bool = False) -> None:
    # Map legacy or internal mode names to human-readable display labels
    _mode_display = {
        "online": "Online",
        "offline": "Offline",
        "integrated": "Online",  # legacy
        "demo": "Offline",       # legacy
    }
    display_label = _mode_display.get(mode_label.lower(), mode_label.upper())
    mode_icon = "🟢" if display_label == "Online" else "🔵"

    if compact:
        html_str = f"""
<div style="
    background: linear-gradient(135deg, #0a1c30 0%, #0e3554 55%, #113f65 100%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px;
    padding: 0.9rem 1.5rem;
    margin: 0 0.5rem 1.2rem;
    display: flex;
    align-items: center;
    gap: 1.2rem;
    box-shadow: 0 8px 28px rgba(10, 28, 48, 0.2);
">
    <div style="flex: 1; min-width: 0;">
        <div style="color: rgba(224,240,255,0.6); font-size: 0.72rem; letter-spacing: 0.14em;
                    text-transform: uppercase; margin-bottom: 0.22rem;">
            BioLens · {html.escape(display_label)} mode
        </div>
        <div style="color: #f0f8ff; font-size: 1.32rem; font-weight: 700;
                    font-family: 'Iowan Old Style', 'Palatino Linotype', serif; letter-spacing: -0.02em;">
            {html.escape(title)}
        </div>
    </div>
    <div style="font-size: 1.5rem; flex-shrink: 0; opacity: 0.75;">{mode_icon}</div>
</div>
"""
    else:
        html_str = f"""
<section class="bl-hero">
<div class="bl-eyebrow">BioLens • {html.escape(display_label)} mode</div>
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
    _fc = chart_font_color()
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 1], tickfont=dict(color=_fc)),
            angularaxis=dict(tickfont=dict(color=_fc)),
            bgcolor='rgba(0,0,0,0)',
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=_fc),
        showlegend=False,
        margin=dict(l=20, r=20, t=20, b=20),
        height=height,
    )
    st.plotly_chart(fig, width="stretch")


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

    # Choose icon based on source type
    if ds == "synthguard-api":
        # Database/API icon
        icon_svg = """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path>
        </svg>"""
    else:
        # CPU/local icon
        icon_svg = """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect>
            <rect x="9" y="9" width="6" height="6"></rect>
            <line x1="9" y1="1" x2="9" y2="4"></line>
            <line x1="15" y1="1" x2="15" y2="4"></line>
            <line x1="9" y1="20" x2="9" y2="23"></line>
            <line x1="15" y1="20" x2="15" y2="23"></line>
            <line x1="20" y1="9" x2="23" y2="9"></line>
            <line x1="20" y1="14" x2="23" y2="14"></line>
            <line x1="1" y1="9" x2="4" y2="9"></line>
            <line x1="1" y1="14" x2="4" y2="14"></line>
        </svg>"""

    return f"""
<div class="bl-data-source-tag" style="background: {style['bg']}; color: {style['fg']}; border: 1px solid {style['fg']}33;">
{icon_svg}
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


def render_alert_card(alert: dict[str, Any]) -> None:
    from services.constants import SEVERITY_STYLES
    sev_color = SEVERITY_STYLES.get(alert.get("severity", "LOW"), {}).get("fg", "#475865")
    
    st.markdown(
        f"""
        <div class="bl-case-card" style="border-left: 4px solid {sev_color};">
            <div class="bl-case-row">
                <div>
                    <div class="bl-case-title" style="color: {sev_color};">{html.escape(alert['title'])}</div>
                    <div class="bl-case-meta">{html.escape(alert['source_type'])} • {html.escape(alert['source_name'])} • {html.escape(alert['region'])}</div>
                </div>
                <div class="bl-badge-row">
                    {severity_badge(alert.get('severity'))}
                    {signal_type_badge(alert.get('signal_type'))}
                    {status_badge(alert.get('status'))}
                </div>
            </div>
            <div style="font-size: 0.95rem; margin-top: 0.4rem; margin-bottom: 0.8rem;">{html.escape(alert['summary'])}</div>
            <div style="font-size: 0.85rem; margin-bottom: 0.4rem;">
                <strong>Confidence:</strong> {alert.get('confidence', 0)}%
            </div>
            <div style="background: rgba(15, 90, 133, 0.08); padding: 0.6rem; border-radius: 6px; font-size: 0.85rem; border-left: 3px solid var(--bl-accent); margin-bottom: 0.6rem;">
                <strong>Screening Relevance:</strong> {html.escape(alert['screening_relevance'])}
            </div>
            <div style="font-size: 0.85rem; color: var(--bl-muted);"><strong>Suggested Action:</strong> {html.escape(alert['suggested_action'])}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_intelligence_context_box(matches: list[dict[str, Any]]) -> None:
    if not matches:
        return
        
    html_parts = ['<div style="background: #fff8e1; border-left: 4px solid #f39c12; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; box-shadow: var(--bl-shadow);">']
    html_parts.append('<div style="font-weight: 700; color: #d35400; margin-bottom: 0.8rem; display: flex; align-items: center; gap: 0.5rem;"><span>⚡</span> External Intelligence Context</div>')
    
    for match in matches:
        priority = match.get("priority", "LOW")
        priority_color = "#e74c3c" if priority == "HIGH" else "#f39c12" if priority == "MEDIUM" else "#3498db"
        
        html_parts.append(f"""
            <div style="margin-bottom: 1rem; padding-bottom: 1rem; border-bottom: 1px solid rgba(0,0,0,0.05);">
                <div style="font-weight: 600; margin-bottom: 0.3rem;">Watchlist Match: {html.escape(match['keyword'])} ({html.escape(match['category'])})</div>
                <div style="font-size: 0.85rem; color: {priority_color}; font-weight: 600; margin-bottom: 0.4rem;">Priority Impact: Review recommended ({priority} Priority)</div>
                <div style="font-size: 0.9rem; color: var(--bl-ink); margin-bottom: 0.4rem;"><strong>Source Alert:</strong> [{html.escape(match['alert_id'])}] {html.escape(match['alert_title'])}</div>
                <div style="font-size: 0.85rem; color: var(--bl-muted);"><em>Relevance: {html.escape(match['screening_relevance'])}</em></div>
            </div>
        """)
        
    html_parts.append('<div style="font-size: 0.8rem; color: var(--bl-muted); font-style: italic;">Note: This context flag is informational. Final decision remains with the analyst.</div>')
    html_parts.append('</div>')
    
    st.markdown("".join(html_parts), unsafe_allow_html=True)


# ── New Dashboard Components ───────────────────────────────────────────────────

def render_threat_posture_banner(posture: dict[str, Any]) -> None:
    """Full-width banner reflecting the current operational threat posture."""
    from services.constants import THREAT_POSTURE_STYLES
    level = posture.get("level", "NORMAL")
    style = THREAT_POSTURE_STYLES.get(level, THREAT_POSTURE_STYLES["NORMAL"])
    score = posture.get("score", 0)
    drivers = posture.get("drivers", [])
    driver_html = "".join(f"<li>{html.escape(d)}</li>" for d in drivers)

    st.markdown(
        f"""
<div style="
    background: {style['bg']};
    border: 2px solid {style['border']};
    border-radius: 16px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: flex-start;
    gap: 1.5rem;
">
    <div style="font-size: 2.5rem; line-height: 1;">{style['icon']}</div>
    <div style="flex: 1;">
        <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 0.4rem;">
            <span style="font-size: 1.2rem; font-weight: 700; color: {style['fg']};">
                Threat Posture: {style['label']}
            </span>
            <span style="font-size: 0.85rem; color: {style['fg']}; font-family: monospace;
                         background: rgba(0,0,0,0.06); padding: 0.2rem 0.6rem; border-radius: 999px;">
                Score {score}/100
            </span>
        </div>
        <ul style="margin: 0; padding-left: 1.2rem; font-size: 0.88rem; color: {style['fg']}; opacity: 0.9;">
            {driver_html}
        </ul>
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_unified_feed_item(item: dict[str, Any]) -> str:
    """Render a single item from the unified activity feed as an HTML string."""
    from services.constants import RISK_COLORS, SEVERITY_STYLES

    ts = format_timestamp(item.get("timestamp", ""))
    title = html.escape(item.get("title", "Untitled"))

    if item["type"] == "screening":
        risk = item.get("risk_level") or "SAFE"
        color = RISK_COLORS.get(risk, "#475865")
        score = item.get("meta", {}).get("hazard_score", 0)
        seq_type = item.get("meta", {}).get("sequence_type", "")
        return f"""
<div style="display:flex; gap:0.8rem; align-items:flex-start; padding:0.6rem 0;
            border-bottom:1px solid var(--bl-border); overflow:hidden;">
    <div style="width:10px; height:10px; border-radius:50%; background:{color};
                margin-top:0.35rem; flex-shrink:0;"></div>
    <div style="flex:1; min-width:0; overflow:hidden;">
        <div style="font-size:0.9rem; font-weight:500; white-space:nowrap; overflow:hidden;
                    text-overflow:ellipsis;">{title}</div>
        <div style="font-size:0.78rem; color:var(--bl-muted);">
            {ts} &nbsp;·&nbsp; {html.escape(seq_type)} &nbsp;·&nbsp; Score {score:.2f}
        </div>
    </div>
    <span style="font-size:0.72rem; font-weight:700; color:{color};
                 background:{color}22; border-radius:999px; padding:0.15rem 0.55rem;
                 white-space:nowrap; flex-shrink:0;">{html.escape(risk)}</span>
</div>"""
    else:
        sev = item.get("severity") or "LOW"
        sev_style = SEVERITY_STYLES.get(sev, {"fg": "#475865", "bg": "#eef2f4"})
        region = item.get("meta", {}).get("region", "Global")
        signal = item.get("meta", {}).get("signal_type", "")
        return f"""
<div style="display:flex; gap:0.8rem; align-items:flex-start; padding:0.6rem 0;
            border-bottom:1px solid var(--bl-border); overflow:hidden;">
    <div style="font-size:1rem; flex-shrink:0; margin-top:0.1rem;">📡</div>
    <div style="flex:1; min-width:0; overflow:hidden;">
        <div style="font-size:0.9rem; font-weight:500; white-space:nowrap; overflow:hidden;
                    text-overflow:ellipsis;">{title}</div>
        <div style="font-size:0.78rem; color:var(--bl-muted);">
            {ts} &nbsp;·&nbsp; {html.escape(region)} &nbsp;·&nbsp; {html.escape(signal)}
        </div>
    </div>
    <span style="font-size:0.72rem; font-weight:700; color:{sev_style['fg']};
                 background:{sev_style['bg']}; border-radius:999px; padding:0.15rem 0.55rem;
                 white-space:nowrap; flex-shrink:0;">{html.escape(sev)}</span>
</div>"""


def render_unified_feed(items: list[dict[str, Any]]) -> None:
    """Render the full unified activity feed panel."""
    if not items:
        st.info("No recent activity to display.")
        return
    parts = [render_unified_feed_item(item) for item in items]
    st.markdown(
        f'<div style="max-height:480px; overflow-y:auto; padding-right:0.3rem;">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


def render_regional_heatmap(regions: list[dict[str, Any]]) -> None:
    """Styled table showing threat regions with severity-weighted colour coding."""
    from services.constants import THREAT_POSTURE_STYLES

    if not regions:
        st.info("No regional threat data available.")
        return

    max_score = max((r.get("threat_score", 0) for r in regions), default=1) or 1

    rows_html = ""
    for r in regions:
        score = r.get("threat_score", 0)
        intensity = score / max_score
        high = r.get("high_count", 0)
        med = r.get("medium_count", 0)
        low = r.get("low_count", 0)

        if high > 0:
            row_bg = f"rgba(220, 53, 69, {0.05 + intensity * 0.25})"
            dot = "🔴"
        elif med > 0:
            row_bg = f"rgba(232, 150, 12, {0.05 + intensity * 0.2})"
            dot = "🟡"
        else:
            row_bg = "rgba(25, 135, 84, 0.05)"
            dot = "🟢"

        signal_types = html.escape((r.get("signal_types") or "").replace(",", " · "))
        rows_html += f"""
<tr style="background:{row_bg};">
    <td style="padding:0.55rem 0.8rem; font-weight:600;">{dot} {html.escape(r['region'])}</td>
    <td style="padding:0.55rem 0.8rem; text-align:center;">{r.get('total_alerts', 0)}</td>
    <td style="padding:0.55rem 0.8rem; text-align:center; color:#dc3545; font-weight:600;">{high or '—'}</td>
    <td style="padding:0.55rem 0.8rem; text-align:center; color:#e8960c;">{med or '—'}</td>
    <td style="padding:0.55rem 0.8rem; font-size:0.8rem; color:var(--bl-muted);">{signal_types}</td>
</tr>"""

    st.markdown(
        f"""
<table style="width:100%; border-collapse:collapse; font-size:0.88rem; border-radius:12px; overflow:hidden;
              border:1px solid var(--bl-border);">
  <thead>
    <tr style="background:rgba(15,90,133,0.08); font-size:0.78rem; text-transform:uppercase;
               letter-spacing:0.06em; color:var(--bl-muted);">
      <th style="padding:0.5rem 0.8rem; text-align:left;">Region</th>
      <th style="padding:0.5rem 0.8rem; text-align:center;">Alerts</th>
      <th style="padding:0.5rem 0.8rem; text-align:center;">HIGH</th>
      <th style="padding:0.5rem 0.8rem; text-align:center;">MED</th>
      <th style="padding:0.5rem 0.8rem; text-align:left;">Signal Types</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
        """,
        unsafe_allow_html=True,
    )


def render_response_time_chart(rt_data: dict[str, Any]) -> None:
    """Plotly histogram of response time distribution by risk tier."""
    import plotly.graph_objects as go

    by_risk = rt_data.get("by_risk", {})
    if not by_risk:
        st.info("No resolved cases with response time data yet.")
        return

    risk_colors = {"HIGH": "#dc3545", "REVIEW": "#e8960c", "SAFE": "#198754"}
    fig = go.Figure()
    for risk, stats in by_risk.items():
        if not stats:
            continue
        fig.add_trace(go.Bar(
            name=risk,
            x=[risk],
            y=[stats.get("mean_hours", 0)],
            error_y=dict(
                type="data",
                array=[max(0, stats.get("p90_hours", 0) - stats.get("mean_hours", 0))],
                visible=True,
            ),
            marker_color=risk_colors.get(risk, "#475865"),
            text=[f"Mean: {stats.get('mean_hours', 0):.1f}h<br>P90: {stats.get('p90_hours', 0):.1f}h<br>n={stats.get('count', 0)}"],
            textposition="outside",
        ))

    _fc = chart_font_color()
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=_fc),
        showlegend=False,
        height=260,
        margin=dict(l=10, r=10, t=10, b=30),
        yaxis_title="Mean Hours",
        yaxis=dict(gridcolor="rgba(0,0,0,0.05)", tickfont=dict(color=_fc)),
        xaxis=dict(showgrid=False, tickfont=dict(color=_fc)),
        bargap=0.4,
    )
    st.plotly_chart(fig, width="stretch")
