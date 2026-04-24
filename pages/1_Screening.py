from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from services import bootstrap_application, get_runtime_mode
from services.model_interface import screen_sequence
from services.storage import save_screening_case
from services.ui import apply_page_style, format_timestamp, render_hero, render_metric_card, risk_badge, render_threat_radar


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
    st.markdown(
        f"""
        <div class="bl-case-card">
            <div class="bl-case-row">
                <div>
                    <div class="bl-case-title">{item['label']}</div>
                    <div class="bl-case-meta">{len(item['sequence'])} residues/bases • {item['sequence_type']}</div>
                </div>
                <div class="bl-badge-row">
                    {risk_badge(result['risk_level'])}
                </div>
            </div>
            <div class="bl-case-meta">Category: {result['category']}</div>
            <p>{result['explanation']}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    metrics = st.columns(3)
    with metrics[0]:
        render_metric_card("Hazard score", f"{result['hazard_score']:.2f}", "Normalized 0.0 to 1.0")
    with metrics[1]:
        render_metric_card("Confidence", f"{result['confidence']:.2f}", "Adapter confidence")
    with metrics[2]:
        render_metric_card("Model", result["model_name"], "Audit-visible identifier")
    if result["baseline_result"]:
        st.caption(f"Baseline comparison: {result['baseline_result']}")
        
    if result.get("threat_breakdown"):
        st.markdown("#### Structured Threat Assessment")
        render_threat_radar(result["threat_breakdown"])


st.set_page_config(page_title="BioLens Screening", layout="wide")
bootstrap_application()
apply_page_style()

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
        submitted = st.form_submit_button("Run Screening", use_container_width=True)

    if submitted:
        try:
            submissions = collect_submissions(sequence_text, uploaded_file)
            run_results: list[dict[str, Any]] = []
            for submission in submissions:
                result = screen_sequence(submission["sequence"], sequence_type)
                run_results.append(
                    {
                        "label": submission["label"],
                        "sequence": submission["sequence"],
                        "sequence_type": sequence_type,
                        "result": result,
                    }
                )
            st.session_state["screening_results"] = run_results
        except ValueError as exc:
            st.error(str(exc))

with guide_col:
    st.subheader("Run Mode")
    st.markdown(
        """
        <div class="bl-panel">
            <p><strong>Mock</strong> returns deterministic local adapter responses for development.</p>
            <p><strong>Demo</strong> behaves like mock mode and auto-loads representative cases into SQLite.</p>
            <p><strong>Integrated</strong> forwards requests to a Synthscreen endpoint while keeping the same contract.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("Safe Handling")
    st.info(
        "BioLens supports defensive screening workflows only. Invalid submissions are rejected and not written to the case database."
    )

results: list[dict[str, Any]] = st.session_state.get("screening_results", [])
if results:
    st.markdown("### Screening Results")
    valid_results = [item for item in results if item["result"]["ok"]]
    invalid_results = [item for item in results if not item["result"]["ok"]]

    for item in valid_results:
        with st.container():
            render_result_card(item)

    for item in invalid_results:
        st.error(f"{item['label']}: {item['result']['error']}")

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
