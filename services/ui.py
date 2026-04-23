from __future__ import annotations

import html
from datetime import datetime

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
