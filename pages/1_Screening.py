from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Any

import streamlit as st

from services import bootstrap_application, get_runtime_mode, get_ui_mode
from services.model_interface import screen_sequence, get_base_url
from services.storage import save_screening_case, update_review
from services.constants import RISK_COLORS
from services.sidebar import render_global_sidebar
from services.ui import (
    apply_page_style,
    format_timestamp,
    render_hero,
    render_verdict_strip,
    render_threat_bars,
    render_error_card,
    render_attributed_sequence,
    render_threat_radar,
    render_primary_risk_drivers,
    render_intelligence_context_box,
)
from services.intelligence import (
    match_case_to_watchlist,
    link_case_to_alert,
    compute_intelligence_risk_modifier,
    get_active_threat_regions,
)
from services.automation import evaluate_auto_rules

def parse_fasta_records(raw_text: str) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    header: str | None = None
    sequence_lines: list[str] = []

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(">"):
            if header is not None:
                if not sequence_lines:
                    raise ValueError(f"FASTA record '{header}' is empty.")
                records.append({"label": header, "sequence": "".join(sequence_lines)})
            header = stripped[1:].strip() or f"record-{len(records) + 1}"
            sequence_lines = []
            continue
        if header is None:
            raise ValueError("Invalid FASTA upload. The first non-empty line must start with '>'.")
        sequence_lines.append(stripped)

    if header is not None:
        if not sequence_lines:
            raise ValueError(f"FASTA record '{header}' is empty.")
        records.append({"label": header, "sequence": "".join(sequence_lines)})

    if not records:
        raise ValueError("No FASTA records were found in the uploaded file.")
    return records


def collect_submissions(sequence_text: str, uploaded_file: Any) -> list[dict[str, str]]:
    if uploaded_file is not None:
        try:
            decoded = uploaded_file.getvalue().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Uploaded FASTA must be valid UTF-8 text.") from exc
        return parse_fasta_records(decoded)

    if sequence_text.strip():
        return [{"label": "Manual sequence", "sequence": sequence_text}]

    raise ValueError("Provide sequence text or upload a FASTA file before screening.")


def render_result_card(item: dict[str, Any]) -> None:
    result = item["result"]
    risk_level = result["risk_level"]
    risk_color = RISK_COLORS.get(risk_level, "transparent")
    intel_modifier = item.get("intel_modifier", 0.0)
    
    modifier_html = ""
    if intel_modifier > 0:
        effective = min(1.0, result["hazard_score"] + intel_modifier)
        modifier_html = f"""
<div style="display:inline-flex; align-items:center; gap:0.4rem; background:rgba(243,156,18,0.12);
            border:1px solid #f39c12; border-radius:6px; padding:0.25rem 0.6rem;
            font-size:0.82rem; font-weight:600; color:#8a4c00; margin-top:0.4rem;">
    ⚡ Intel Modifier: +{intel_modifier:.3f} → Effective Score: {effective:.3f}
</div>"""
    
    card_html = f"""
<div class="bl-result-card" style="border-left: 6px solid {risk_color};">
<div class="bl-result-card-inner">
<div style="font-weight: 600; font-size: 1.1rem; margin-bottom: 0.3rem;">{html.escape(item['label'])}</div>
<div style="font-size: 0.85rem; color: var(--bl-muted); margin-bottom: 1.2rem;">
                    {len(item['sequence'])} residues/bases • {html.escape(item['sequence_type'])} • Category: {html.escape(result['category'])}
</div>
{render_verdict_strip(result)}
{modifier_html}
<p style="margin-top: 1rem; margin-bottom: 0;">{html.escape(result['explanation'])}</p>
</div>
</div>
        """
    st.markdown(card_html.replace("\n", " "), unsafe_allow_html=True)
    
    col1, col2 = st.columns([1.0, 1.2], gap="large")
    with col1:
        st.markdown("#### Threat Radar")
        render_threat_radar(result.get("threat_breakdown"), height=240)
    with col2:
        st.markdown("#### Structured Threat Assessment")
        render_threat_bars(result.get("threat_breakdown"))

    st.markdown("#### Primary Risk Drivers")
    render_primary_risk_drivers(result.get("threat_breakdown"))

    if "intelligence_matches" in item:
        render_intelligence_context_box(item["intelligence_matches"])
        
    st.markdown("<div style='margin-bottom: 1.5rem;'></div>", unsafe_allow_html=True)
    st.markdown("#### Sequence Highlight")
    render_attributed_sequence(item["sequence"], result.get("attribution_data"))


st.set_page_config(page_title="BioLens Screening", layout="wide")
bootstrap_application()
apply_page_style()
render_global_sidebar()

mode = get_runtime_mode()
saved_case_ids = st.session_state.pop("saved_case_ids", [])

render_hero(
    "Screening",
    "Submit DNA or protein sequences, run the adapter contract, inspect the returned triage result, and save valid outputs into the review queue.",
    mode,
)

# Pre-screening threat context banner (full mode only — compact keeps the flow clean)
if get_ui_mode() == "full":
    threat_regions = get_active_threat_regions()
    if threat_regions:
        region_names = ", ".join(r["region"] for r in threat_regions[:3])
        st.warning(
            f"⚡ **Active HIGH-Severity Alerts** in: **{region_names}**. "
            f"Watchlist matching is active — relevant sequences will be flagged automatically."
        )

if saved_case_ids:
    ids_text = ", ".join(case_id[:8] for case_id in saved_case_ids)
    st.success(f"Saved {len(saved_case_ids)} case(s) at {format_timestamp(st.session_state.get('last_save_time'))}: {ids_text}")

input_col, guide_col = st.columns([1.2, 0.8], gap="large")

with input_col:
    with st.form("screening-form"):
        st.subheader("Intake")
        sequence_type = st.selectbox("Sequence type", ["DNA", "PROTEIN"], index=0)
        sequence_text = st.text_area(
            "Paste sequence",
            height=220,
            placeholder="Paste raw sequence text here. Whitespace is ignored.",
        )
        uploaded_file = st.file_uploader("Or upload FASTA", type=["fa", "fasta", "faa", "txt"])
        submitted = st.form_submit_button("Run Screening", type="primary", use_container_width=True)

    if submitted:
        try:
            submissions = collect_submissions(sequence_text, uploaded_file)
            run_results: list[dict[str, Any]] = []
            
            progress_bar = st.progress(0, text="Screening sequences...")
            for i, submission in enumerate(submissions):
                result = screen_sequence(submission["sequence"], sequence_type)
                
                intel_matches = match_case_to_watchlist({
                    "category": result.get("category", ""),
                    "explanation": result.get("explanation", ""),
                    "sequence_type": sequence_type,
                })
                intel_modifier = compute_intelligence_risk_modifier(intel_matches)
                
                run_results.append(
                    {
                        "label": submission["label"],
                        "sequence": submission["sequence"],
                        "sequence_type": sequence_type,
                        "result": result,
                        "intelligence_matches": intel_matches,
                        "intel_modifier": intel_modifier,
                    }
                )
                progress_bar.progress((i + 1) / len(submissions), text=f"Screened {i + 1} of {len(submissions)} sequences...")
            
            progress_bar.empty()
            st.session_state["screening_results"] = run_results
            
            if "biolens-validation" in [r["result"].get("data_source") for r in run_results if not r["result"].get("ok")]:
                st.error("Some sequences failed validation. Please fix and resubmit.")
                
        except ValueError as exc:
            render_error_card("Input Validation Failed", str(exc))

with guide_col:
    st.subheader("Screening Mode")
    endpoint_display = get_base_url()

    if mode == "online":
        mode_detail = f"""
<div class="bl-panel">
<p><strong>🟢 Online Mode</strong><br>
All sequences — DNA and protein — are screened by the <strong>live SynthGuard API</strong>.<br>
<code style="font-size:0.8rem;">{html.escape(endpoint_display)}</code></p>
<p style="margin-bottom:0;">Results carry the <strong>SynthGuard API</strong> data source tag and reflect real model predictions.</p>
</div>
"""
    else:
        mode_detail = """
<div class="bl-panel">
<p><strong>🔵 Offline Mode</strong><br>
All sequences — DNA and protein — are screened by <strong>BioLens' built-in heuristic engine</strong>.
No internet connection required.</p>
<p style="margin-bottom:0;">Results carry the <strong>BioLens Heuristic</strong> data source tag. Switch to Online in System Admin to use the live API.</p>
</div>
"""

    st.markdown(mode_detail.replace("\n", " "), unsafe_allow_html=True)
    st.subheader("Safe Handling")
    st.info(
        "BioLens supports defensive screening workflows only. Invalid submissions are rejected and not written to the case database."
    )

results: list[dict[str, Any]] = st.session_state.get("screening_results", [])
if results:
    st.markdown("### Screening Results")
    valid_results = [item for item in results if item["result"]["ok"]]
    invalid_results = [item for item in results if not item["result"]["ok"]]

    if len(results) > 1:
        highs = sum(1 for r in valid_results if r["result"]["risk_level"] == "HIGH")
        reviews = sum(1 for r in valid_results if r["result"]["risk_level"] == "REVIEW")
        safes = sum(1 for r in valid_results if r["result"]["risk_level"] == "SAFE")
        fails = len(invalid_results)
        
        summary_html = f"""
<div style="display: flex; gap: 1rem; align-items: center; background: rgba(255,255,255,0.5); padding: 0.8rem 1.2rem; border-radius: 12px; margin-bottom: 1.5rem; border: 1px solid var(--bl-border);">
<div style="font-weight: 600;">{len(results)} sequences screened:</div>
<div style="display: flex; gap: 0.5rem; align-items: center;"><span style="color: #dc3545; font-size: 1.2rem;">●</span> {highs} HIGH</div>
<div style="display: flex; gap: 0.5rem; align-items: center;"><span style="color: #e8960c; font-size: 1.2rem;">●</span> {reviews} REVIEW</div>
<div style="display: flex; gap: 0.5rem; align-items: center;"><span style="color: #198754; font-size: 1.2rem;">●</span> {safes} SAFE</div>
            {f'<div style="display: flex; gap: 0.5rem; align-items: center; margin-left: auto; color: #e74c3c;"><span style="font-size: 1.2rem;">⚠️</span> {fails} FAILED</div>' if fails > 0 else ''}
</div>
        """
        st.markdown(summary_html.replace("\n", " "), unsafe_allow_html=True)

    for item in invalid_results:
        err_msg = item['result'].get('error', 'Unknown error')
        ds = item['result'].get('data_source', '')
        
        title = f"Failed to screen {html.escape(item['label'])}"
        
        if "timeout" in err_msg.lower() or "connection" in err_msg.lower():
            title = f"SynthGuard API Unavailable ({html.escape(item['label'])})"
            err_msg += " You can retry the request, or switch the BioLens Mode to 'offline' to use the local triage engine."
            
        render_error_card(title, err_msg)

    for item in valid_results:
        with st.container():
            render_result_card(item)

    if valid_results:
        if st.button("Save Valid Results to Inbox", type="primary", use_container_width=True):
            saved_ids = []
            auto_escalated = 0
            for item in valid_results:
                case_id = save_screening_case(
                    sequence_text=item["sequence"],
                    sequence_type=item["sequence_type"],
                    result=item["result"],
                )
                saved_ids.append(case_id)
                
                intel_matches = item.get("intelligence_matches", [])
                if intel_matches:
                    for match in intel_matches:
                        link_case_to_alert(case_id, match["alert_id"], match["watchlist_id"], match["match_reason"])
                    
                    # Evaluate automation rules
                    fired_rules = evaluate_auto_rules(case_id, intel_matches)
                    if fired_rules:
                        # Apply the highest-priority rule's target status
                        top_rule = fired_rules[0]
                        if top_rule["target_status"] in ("ESCALATED", "IN_REVIEW"):
                            update_review(
                                screening_id=case_id,
                                analyst_status=top_rule["target_status"],
                                analyst_notes=f"Auto-set by rule: {top_rule['rule_name']}",
                                final_action=None,
                            )
                            auto_escalated += 1
                        
            st.session_state["saved_case_ids"] = saved_ids
            st.session_state["last_save_time"] = datetime.now().astimezone().isoformat()
            st.session_state["screening_results"] = []
            if auto_escalated:
                st.session_state["auto_escalated_count"] = auto_escalated
            st.rerun()

auto_esc = st.session_state.pop("auto_escalated_count", 0)
if auto_esc:
    st.warning(f"⚡ **{auto_esc} case(s) auto-escalated** by intelligence automation rules.")
