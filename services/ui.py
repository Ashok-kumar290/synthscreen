from __future__ import annotations

import html
from datetime import datetime
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from services.constants import ACTION_STYLES, RISK_STYLES, STATUS_STYLES


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

            .bl-panel, .bl-case-card, .bl-metric-card {
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
        </style>
        """,
        unsafe_allow_html=True,
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
    st.markdown(
        f"""
        <section class="bl-hero">
            <div class="bl-eyebrow">BioLens • {html.escape(mode_label.upper())} mode</div>
            <h1>{html.escape(title)}</h1>
            <p>{html.escape(subtitle)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: str, detail: str) -> None:
    st.markdown(
        f"""
        <div class="bl-metric-card">
            <div class="bl-metric-label">{html.escape(label)}</div>
            <div class="bl-metric-value">{html.escape(value)}</div>
            <div class="bl-metric-detail">{html.escape(detail)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_timestamp(value: str | None) -> str:
    if not value:
        return "Pending"

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.astimezone().strftime("%d %b %Y, %H:%M")


def render_threat_radar(breakdown: dict[str, Any] | None) -> None:
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
        margin=dict(l=40, r=40, t=20, b=20),
        height=320,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_attributed_sequence(sequence: str, attribution_data: dict[str, Any] | None) -> None:
    if not attribution_data or not attribution_data.get("positions"):
        st.code(sequence, language="text", wrap_lines=True)
        return

    positions = set(attribution_data.get("positions", []))
    scores = attribution_data.get("scores", [])
    pos_to_score = dict(zip(attribution_data.get("positions", []), scores))

    html_parts = ['<div class="bl-sequence-preview" style="line-height: 1.6; word-break: break-all; font-family: monospace;">']
    
    for i, char in enumerate(sequence):
        if i in positions:
            score = pos_to_score.get(i, 0)
            # Red highlight based on score
            bg_color = f"rgba(231, 76, 60, {min(score, 1.0) * 0.85})"
            html_parts.append(f'<span style="background-color: {bg_color}; border-radius: 2px; padding: 0 1px;" title="Attribution: {score:.2f}">{char}</span>')
        else:
            html_parts.append(char)
            
    html_parts.append('</div>')
    st.markdown("".join(html_parts), unsafe_allow_html=True)
    
    regions = attribution_data.get("regions", [])
    if regions:
        st.markdown("<div style='margin-top: 0.5rem; font-size: 0.85rem; color: var(--bl-muted);'><strong>Highlighted Regions:</strong></div>", unsafe_allow_html=True)
        for r in regions:
            st.markdown(f"<div style='font-size: 0.8rem; margin-top: 0.2rem;'>• {r['label']} (Pos {r['start']}-{r['end']}, Score {r['score']:.2f})</div>", unsafe_allow_html=True)
