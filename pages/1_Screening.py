from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Any

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.model_interface import screen_sequence
from services.storage import save_screening_case
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
)

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
    
    card_html = f"""
<div class="bl-result-card" style="border-left: 6px solid {risk_color};">
<div class="bl-result-card-inner">
<div style="font-weight: 600; font-size: 1.1rem; margin-bottom: 0.3rem;">{html.escape(item['label'])}</div>
<div style="font-size: 0.85rem; color: var(--bl-muted); margin-bottom: 1.2rem;">
                    {len(item['sequence'])} residues/bases • {html.escape(item['sequence_type'])} • Category: {html.escape(result['category'])}
</div>
{render_verdict_strip(result)}
<p style="margin-top: 1rem; margin-bottom: 0;">{html.escape(result['explanation'])}</p>
</div>
</div>
        """
    st.markdown(card_html.replace("\n", " "), unsafe_allow_html=True)
    
    col1, col2 = st.columns([1.1, 0.9], gap="large")
    with col1:
        st.markdown("#### Structured Threat Assessment")
        render_threat_bars(result.get("threat_breakdown"))
    with col2:
        st.markdown("#### Baseline Comparison")
        if result.get("baseline_result"):
            st.info(result["baseline_result"])
        else:
            st.markdown("<p style='color: var(--bl-muted); font-size: 0.9rem;'>No baseline comparison available.</p>", unsafe_allow_html=True)
            
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
                run_results.append(
                    {
                        "label": submission["label"],
                        "sequence": submission["sequence"],
                        "sequence_type": sequence_type,
                        "result": result,
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
    st.subheader("Run Mode")
    endpoint_display = os.environ.get("SYNTHSCREEN_ENDPOINT", "https://seyomi-synthguard-api.hf.space/biolens/screen")
    card_html = f"""
<div class="bl-panel">
<p><strong>Integrated</strong> forwards DNA requests to a live Track 1 API (currently set to <code>{html.escape(endpoint_display)}</code>). Protein requests transparently use the local mock engine.</p>
<p><strong>Mock/Demo</strong> uses local mock generation.</p>
<p>Current Mode: <strong style="color: var(--bl-accent);">{mode.upper()}</strong></p>
<p style="font-size: 0.85rem; color: var(--bl-muted); margin-top: 0.5rem;">To change the API endpoint or switch to mock mode, visit the ⚙️ System Admin settings on the main overview page.</p>
</div>
"""
    st.markdown(card_html.replace("\n", " "), unsafe_allow_html=True)
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
            err_msg += " You can retry the request, or switch the BioLens Mode to 'mock' to use the local heuristic engine."
            
        render_error_card(title, err_msg)

    for item in valid_results:
        with st.container():
            render_result_card(item)

    if valid_results:
        if st.button("Save Valid Results to Inbox", type="primary", use_container_width=True):
            saved_ids = []
            for item in valid_results:
                saved_ids.append(
                    save_screening_case(
                        sequence_text=item["sequence"],
                        sequence_type=item["sequence_type"],
                        result=item["result"],
                    )
                )
            st.session_state["saved_case_ids"] = saved_ids
            st.session_state["last_save_time"] = datetime.now().astimezone().isoformat()
            st.session_state["screening_results"] = []
            st.rerun()
