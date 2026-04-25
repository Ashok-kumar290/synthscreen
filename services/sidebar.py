from __future__ import annotations

import os
from urllib import error, request

import streamlit as st

from services import get_runtime_mode
from services.export import build_export_dataset, export_filename, export_screenings_csv, export_screenings_json
from services.seed_data import ensure_demo_cases, load_sample_dataset
from services.storage import reset_database
from services.model_interface import get_base_url
_HEALTH_ENDPOINT_SUFFIX = "/health"


def _derive_health_url(biolens_endpoint: str) -> str:
    """Derive the /health URL from the configured BioLens screen endpoint."""
    # Strip known path suffixes to get the base URL
    for suffix in ("/biolens/screen", "/screen", "/protein/screen"):
        if biolens_endpoint.endswith(suffix):
            return biolens_endpoint[: -len(suffix)] + _HEALTH_ENDPOINT_SUFFIX
    return biolens_endpoint.rstrip("/") + _HEALTH_ENDPOINT_SUFFIX


def _check_api_health(endpoint: str) -> tuple[bool, str]:
    """Ping the API health endpoint. Returns (is_healthy, message)."""
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

    with st.sidebar:
        # ── User Role ────────────────────────────────────────────────
        st.markdown("### User Role")
        role = st.radio(
            "Access Level",
            ["Analyst", "Supervisor"],
            index=0 if current_role == "Analyst" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state["user_role"] = role

        # ── Threat Posture Indicator ──────────────────────────────────
        try:
            from services.dashboard import compute_threat_posture
            from services.constants import THREAT_POSTURE_STYLES
            posture = compute_threat_posture()
            p_style = THREAT_POSTURE_STYLES.get(posture["level"], THREAT_POSTURE_STYLES["NORMAL"])
            st.markdown(
                f"""
                <div style="background:{p_style['bg']}; border:1px solid {p_style['border']};
                            border-radius:8px; padding:0.5rem 0.75rem; margin-top:0.8rem;
                            font-size:0.82rem; font-weight:600; color:{p_style['fg']};
                            display:flex; align-items:center; gap:0.4rem;">
                    {p_style['icon']} Posture: {p_style['label']}
                    <span style="margin-left:auto; font-family:monospace; font-size:0.75rem;">{posture['score']}/100</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
        except Exception:
            pass

        # ── Active Intel Alert Banner ─────────────────────────────────
        from services.intelligence import list_alerts
        all_alerts_sidebar = list_alerts()
        active_alerts_sidebar = [a for a in all_alerts_sidebar if a["status"] not in ("DISMISSED", "REVIEWED")]
        active_alerts = len(active_alerts_sidebar)
        if active_alerts > 0:
            st.markdown(
                f"""
                <div style="background: rgba(231, 76, 60, 0.1); border-left: 3px solid #e74c3c;
                            padding: 0.5rem; border-radius: 4px; margin-top: 0.6rem; font-size: 0.85rem;">
                    <strong>{active_alerts} Active Intel Signal{'s' if active_alerts > 1 else ''}</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )
            # Quick Intel — most urgent alert
            high_sidebar = [a for a in active_alerts_sidebar if a["severity"] == "HIGH"]
            top_alert = high_sidebar[0] if high_sidebar else active_alerts_sidebar[0]
            title_truncated = top_alert['title'][:50] + ('…' if len(top_alert['title']) > 50 else '')
            st.markdown(
                f"""
                <div style="background:rgba(243,156,18,0.06); border:1px solid #f39c12;
                            border-radius:6px; padding:0.45rem 0.65rem; margin-top:0.4rem;
                            font-size:0.78rem; color:#8a4c00;">
                    <strong>⚡ {top_alert['severity']}</strong> · {title_truncated}
                </div>
                """,
                unsafe_allow_html=True,
            )

        # ── System Admin ─────────────────────────────────────────────
        with st.expander("⚙️ System Admin"):

            # — Screening Mode —
            st.markdown("**Screening Mode**")
            mode_labels = {
                "online": "🟢 Online — Live SynthGuard API",
                "offline": "🔵 Offline — BioLens local heuristic",
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

            # Mode description
            if new_mode == "online":
                st.caption(
                    "All sequences (DNA & protein) are screened by the live SynthGuard API. "
                    "Requires internet connectivity."
                )
            else:
                st.caption(
                    "All sequences are screened by BioLens' built-in heuristic engine. "
                    "Works fully offline — no internet required."
                )

            if new_mode != mode:
                os.environ["BIOLENS_MODE"] = new_mode
                st.rerun()

            # — API Configuration (only in Online mode) —
            if new_mode == "online":
                st.markdown("---")
                st.markdown("**API Configuration**")
                endpoint = get_base_url()
                new_endpoint = st.text_input("Endpoint URL", value=endpoint, key="endpoint_input")
                if new_endpoint != endpoint:
                    os.environ["SYNTHSCREEN_ENDPOINT"] = new_endpoint
                    st.rerun()

                # Health check
                if st.button("🔍 Check Connection", use_container_width=True, key="health_check_btn"):
                    with st.spinner("Checking…"):
                        healthy, msg = _check_api_health(new_endpoint)
                    if healthy:
                        st.success(f"✅ {msg}")
                    else:
                        st.error(f"❌ {msg}")

            # — Data Management —
            st.markdown("---")
            st.markdown("**Data Management**")

            if st.button("📦 Load Sample Dataset", use_container_width=True, key="load_sample_btn"):
                result = load_sample_dataset()
                if result["inserted"] > 0:
                    st.success(f"Loaded {result['inserted']} sample case(s).")
                else:
                    st.info("Sample cases already present — nothing new to load.")

            if st.button("🌱 Load Demo Cases", use_container_width=True, key="load_demo_btn"):
                result = ensure_demo_cases()
                if result["inserted"] > 0:
                    st.success(f"Loaded {result['inserted']} demo case(s).")
                else:
                    st.info("Demo cases already present.")

            if st.button("🗑️ Reset All Data", use_container_width=True, type="secondary", key="reset_btn"):
                if st.session_state.get("confirm_reset"):
                    reset_database()
                    st.session_state["confirm_reset"] = False
                    st.success("Database cleared.")
                    st.rerun()
                else:
                    st.session_state["confirm_reset"] = True
                    st.warning("Click again to confirm reset.")

            # — Export Data —
            st.markdown("---")
            st.markdown("**Export Data**")
            export_records = build_export_dataset()
            st.download_button(
                "⬇️ Download CSV",
                data=export_screenings_csv(export_records),
                file_name=export_filename("biolens_cases", "csv"),
                mime="text/csv",
                use_container_width=True,
                key="export_csv_btn",
            )
            st.download_button(
                "⬇️ Download JSON",
                data=export_screenings_json(export_records),
                file_name=export_filename("biolens_cases", "json"),
                mime="application/json",
                use_container_width=True,
                key="export_json_btn",
            )
