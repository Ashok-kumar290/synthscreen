import os

import streamlit as st

from services import get_runtime_mode
from services.export import build_export_dataset, export_filename, export_screenings_csv, export_screenings_json
from services.seed_data import ensure_demo_cases, load_sample_dataset
from services.storage import reset_database


def render_global_sidebar() -> None:
    current_role = st.session_state.get("user_role", "Analyst")
    mode = get_runtime_mode()

    with st.sidebar:
        st.markdown("### User Role")
        role = st.radio(
            "Access Level",
            ["Analyst", "Supervisor"],
            index=0 if current_role == "Analyst" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state["user_role"] = role

        # Streamlit automatically adds page navigation below this if there is no explicit st.navigation.
        # But to ensure Admin Settings are below navigation, we don't have control over native menu order 
        # unless we use st.navigation. Streamlit native navigation places itself at the top of the sidebar.
        # So our custom elements here will naturally fall below the native navigation links.

        with st.expander("⚙️ System Admin"):
            st.markdown("**API Settings**")
            mode_options = ["integrated", "mock", "demo"]
            current_mode_idx = mode_options.index(mode) if mode in mode_options else 0
            new_mode = st.radio("System Mode", mode_options, index=current_mode_idx, horizontal=True)
            if new_mode != mode:
                os.environ["BIOLENS_MODE"] = new_mode
                st.rerun()

            endpoint = os.environ.get("SYNTHSCREEN_ENDPOINT", "https://seyomi-synthguard-api.hf.space/biolens/screen")
            new_endpoint = st.text_input("Track 1 API Endpoint", value=endpoint)
            if new_endpoint != endpoint:
                os.environ["SYNTHSCREEN_ENDPOINT"] = new_endpoint
                st.rerun()

            st.markdown("**Data Management**")
            if st.button("📦 Import Sample Dataset", use_container_width=True):
                result = load_sample_dataset()
                st.success(f"Sample data loaded. Inserted {result['inserted']} case(s).")

            if st.button("🗑️ Reset All Data", use_container_width=True, type="secondary"):
                if st.session_state.get("confirm_reset"):
                    reset_database()
                    st.session_state["confirm_reset"] = False
                    st.success("Database cleared.")
                    st.rerun()
                else:
                    st.session_state["confirm_reset"] = True
                    st.warning("Click again to confirm.")

            if not st.session_state.get("confirm_reset", False):
                if st.button("Load Demo Cases", use_container_width=True):
                    result = ensure_demo_cases()
                    st.success("Demo data synced.")

            st.markdown("**Export Data**")
            export_records = build_export_dataset()
            st.download_button(
                "Download CSV",
                data=export_screenings_csv(export_records),
                file_name=export_filename("biolens_cases", "csv"),
                mime="text/csv",
                use_container_width=True,
            )
            st.download_button(
                "Download JSON",
                data=export_screenings_json(export_records),
                file_name=export_filename("biolens_cases", "json"),
                mime="application/json",
                use_container_width=True,
            )
