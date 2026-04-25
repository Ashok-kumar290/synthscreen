from __future__ import annotations

import os
from urllib import error, request

import streamlit as st

from services import get_runtime_mode, get_ui_mode
from services.constants import COMPACT_PAGES, FULL_PAGES
from services.export import build_export_dataset, export_filename, export_screenings_csv, export_screenings_json
from services.seed_data import ensure_demo_cases, load_sample_dataset
from services.storage import reset_database
from services.model_interface import get_base_url

_HEALTH_ENDPOINT_SUFFIX = "/health"

_POSTURE_DARK = {
    "NORMAL":   {"bg": "rgba(31,106,77,0.18)",   "border": "rgba(76,175,130,0.35)",  "fg": "#4caf82", "label": "Normal Operations"},
    "ELEVATED": {"bg": "rgba(138,76,0,0.18)",     "border": "rgba(232,150,12,0.35)",  "fg": "#f0a030", "label": "Elevated Caution"},
    "HIGH":     {"bg": "rgba(143,36,36,0.20)",    "border": "rgba(220,53,69,0.40)",   "fg": "#f06060", "label": "High Alert"},
}


def _derive_health_url(biolens_endpoint: str) -> str:
    for suffix in ("/biolens/screen", "/screen", "/protein/screen"):
        if biolens_endpoint.endswith(suffix):
            return biolens_endpoint[: -len(suffix)] + _HEALTH_ENDPOINT_SUFFIX
    return biolens_endpoint.rstrip("/") + _HEALTH_ENDPOINT_SUFFIX


def _check_api_health(endpoint: str) -> tuple[bool, str]:
    health_url = _derive_health_url(endpoint)
    try:
        req = request.Request(health_url, method="GET")
        with request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, "API reachable"
            return False, f"API returned status {resp.status}"
    except error.URLError as exc:
        if "timed out" in str(exc.reason).lower():
            return False, "API timed out (may be waking up)"
        return False, f"Cannot reach API: {exc.reason}"
    except Exception as exc:
        return False, f"Health check failed: {exc}"


def render_global_sidebar() -> None:
    current_role = st.session_state.get("user_role", "Analyst")
    mode = get_runtime_mode()
    ui_mode = get_ui_mode()

    with st.sidebar:
        # ── View Mode ─────────────────────────────────────────────────
        selected_ui = st.radio(
            "View",
            ["compact", "full"],
            index=0 if ui_mode == "compact" else 1,
            format_func=lambda m: "Compact" if m == "compact" else "Full",
            horizontal=True,
            label_visibility="collapsed",
            key="sidebar_ui_mode",
        )
        if selected_ui != ui_mode:
            os.environ["BIOLENS_UI_MODE"] = selected_ui
            st.rerun()

        # ── Navigation ────────────────────────────────────────────────
        pages = COMPACT_PAGES if ui_mode == "compact" else FULL_PAGES
        for page_path, label in pages:
            st.page_link(page_path, label=label)

        st.markdown("---")

        # ── User Role ─────────────────────────────────────────────────
        st.markdown("### User Role")
        role = st.radio(
            "Access Level",
            ["Analyst", "Supervisor"],
            index=0 if current_role == "Analyst" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state["user_role"] = role

        # ── Threat Posture ────────────────────────────────────────────
        try:
            from services.dashboard import compute_threat_posture
            posture = compute_threat_posture()
            p = _POSTURE_DARK.get(posture["level"], _POSTURE_DARK["NORMAL"])
            st.markdown(
                f'<div style="background:{p["bg"]}; border:1px solid {p["border"]}; '
                f'border-radius:8px; padding:0.5rem 0.75rem; margin-top:0.8rem; '
                f'font-size:0.82rem; font-weight:600; color:{p["fg"]}; '
                f'display:flex; align-items:center;">'
                f'Posture: {p["label"]}'
                f'<span style="margin-left:auto; font-family:monospace; font-size:0.75rem;">'
                f'{posture["score"]}/100</span></div>',
                unsafe_allow_html=True,
            )
        except Exception:
            st.markdown(
                '<div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.1); '
                'border-radius:8px; padding:0.5rem 0.75rem; margin-top:0.8rem; '
                'font-size:0.82rem; color:#8899a6;">Posture: unavailable</div>',
                unsafe_allow_html=True,
            )

        # ── Active Intel Signals ──────────────────────────────────────
        from services.intelligence import list_alerts
        all_alerts_sidebar = list_alerts()
        active_alerts_sidebar = [a for a in all_alerts_sidebar if a["status"] not in ("DISMISSED", "REVIEWED")]
        active_alerts = len(active_alerts_sidebar)
        if active_alerts > 0:
            st.markdown(
                f'<div style="background:rgba(220,53,69,0.12); border-left:3px solid #e74c3c; '
                f'padding:0.5rem; border-radius:4px; margin-top:0.6rem; font-size:0.85rem; color:#f06060;">'
                f'<strong>{active_alerts} Active Intel Signal{"s" if active_alerts > 1 else ""}</strong></div>',
                unsafe_allow_html=True,
            )
            high_sidebar = [a for a in active_alerts_sidebar if a["severity"] == "HIGH"]
            top_alert = high_sidebar[0] if high_sidebar else active_alerts_sidebar[0]
            title_truncated = top_alert["title"][:50] + ("…" if len(top_alert["title"]) > 50 else "")
            st.markdown(
                f'<div style="background:rgba(243,156,18,0.08); border:1px solid rgba(243,156,18,0.3); '
                f'border-radius:6px; padding:0.45rem 0.65rem; margin-top:0.4rem; '
                f'font-size:0.78rem; color:#f0a030;">'
                f'<strong>{top_alert["severity"]}</strong> · {title_truncated}</div>',
                unsafe_allow_html=True,
            )

        # ── System Admin ──────────────────────────────────────────────
        with st.expander("System Admin"):

            st.markdown("**Screening Mode**")
            mode_labels = {
                "online":  "Online — Live SynthGuard API",
                "offline": "Offline — BioLens local heuristic",
            }
            mode_display = [mode_labels["online"], mode_labels["offline"]]
            current_idx = 0 if mode == "online" else 1
            selected_display = st.radio(
                "mode_select",
                mode_display,
                index=current_idx,
                label_visibility="collapsed",
            )
            new_mode = "online" if selected_display == mode_labels["online"] else "offline"

            if new_mode == "online":
                st.caption("Sequences screened by the live SynthGuard API. Requires internet connectivity.")
            else:
                st.caption("Sequences screened by the built-in heuristic engine. Works fully offline.")

            if new_mode != mode:
                os.environ["BIOLENS_MODE"] = new_mode
                st.rerun()

            if new_mode == "online":
                st.markdown("---")
                st.markdown("**API Configuration**")
                endpoint = get_base_url()
                new_endpoint = st.text_input("Endpoint URL", value=endpoint, key="endpoint_input")
                if new_endpoint != endpoint:
                    os.environ["SYNTHSCREEN_ENDPOINT"] = new_endpoint
                    st.rerun()

                if st.button("Check Connection", use_container_width=True, key="health_check_btn"):
                    with st.spinner("Checking…"):
                        healthy, msg = _check_api_health(new_endpoint)
                    st.session_state["_health_result"] = (healthy, msg)

                if "_health_result" in st.session_state:
                    h_ok, h_msg = st.session_state["_health_result"]
                    if h_ok:
                        st.success(f"Connected: {h_msg}")
                    else:
                        st.error(f"Unreachable: {h_msg}")

            st.markdown("---")
            st.markdown("**Data Management**")

            if st.button("Load Sample Dataset", use_container_width=True, key="load_sample_btn"):
                result = load_sample_dataset()
                if result["inserted"] > 0:
                    st.success(f"Loaded {result['inserted']} sample case(s).")
                else:
                    st.info("Sample cases already present.")

            if st.button("Load Demo Cases", use_container_width=True, key="load_demo_btn"):
                result = ensure_demo_cases()
                if result["inserted"] > 0:
                    st.success(f"Loaded {result['inserted']} demo case(s).")
                else:
                    st.info("Demo cases already present.")

            if st.button("Reset All Data", use_container_width=True, type="secondary", key="reset_btn"):
                if st.session_state.get("confirm_reset"):
                    reset_database()
                    st.session_state["confirm_reset"] = False
                    st.success("Database cleared.")
                    st.rerun()
                else:
                    st.session_state["confirm_reset"] = True
                    st.warning("Click again to confirm reset.")

            st.markdown("---")
            st.markdown("**Export Data**")
            export_records = build_export_dataset()
            st.download_button(
                "Download CSV",
                data=export_screenings_csv(export_records),
                file_name=export_filename("biolens_cases", "csv"),
                mime="text/csv",
                use_container_width=True,
                key="export_csv_btn",
            )
            st.download_button(
                "Download JSON",
                data=export_screenings_json(export_records),
                file_name=export_filename("biolens_cases", "json"),
                mime="application/json",
                use_container_width=True,
                key="export_json_btn",
            )
