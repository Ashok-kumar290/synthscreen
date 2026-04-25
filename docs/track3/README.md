# BioLens Dashboard (Track 3)

BioLens is an operational dashboard designed for function-aware biosecurity screening. Built as the practitioner-facing interface for the Synthscreen adapter layer, BioLens handles sequence intake, triage, review workflows, analytics, and intelligence reporting. 

It specifically addresses the operational needs of biosecurity analysts by abstracting the complex underlying models into a highly readable, interactive, and offline-ready Streamlit application.

## Key Features

### 1. Sequence Intake & Triage
- **Flexible Input:** Paste raw DNA/protein sequences directly or upload FASTA files.
- **Immediate Triage:** Connects to the Synthscreen adapter to evaluate sequences, automatically assigning a risk tier, hazard score, and confidence rating.
- **Sequence-Level Interpretability:** Visually highlights attributed residues and critical substrings, allowing analysts to quickly pinpoint the hazardous segments within a sequence.

### 2. Threat Assessment Radar
- **Multi-Dimensional Analysis:** Breaks down flagged threats into visual radar charts (e.g., Toxicity, Pathogenicity, Environmental Risk).
- **Rapid Decision Making:** Transforms raw hazard scores into structured insights that make the "why" behind a flag instantly clear.

### 3. Analyst Review Workflow & Inbox
- **Actionable Inbox:** All valid screened cases are routed into a local SQLite-backed inbox for persistent tracking.
- **Case State Management:** Analysts can progress case statuses through `NEW`, `IN_REVIEW`, and `ESCALATED`.
- **Final Actions:** Cases can be assigned definitive outcomes such as `APPROVE`, `REJECT`, or `MODIFY`, complete with detailed analyst notes.

### 4. Biosecurity Intelligence Feed
- **Live Context:** A dedicated intelligence page provides up-to-date policy and regulatory guidelines that shape the screening thresholds.
- **Alerts & Research:** Displays emerging biosecurity alerts and recent research insights, keeping practitioners informed on the broader landscape.

### 5. Analytics & Audit Trails
- **Operational Metrics:** High-level dashboard views for tracked metrics like average hazard score, flagged case volume, and open queue status.
- **Event Auditing:** Every state change and analyst action is recorded as an immutable audit event attached to the specific case.
- **Exporting Capabilities:** Case histories and complete audit trails can be exported entirely as CSV or JSON formats for external compliance reviews.

### 6. Local-First & Configurable Runtime
- **Deployment Modes:** Supports `Mock` mode for UI development, `Demo` mode with pre-loaded representative data, and `Integrated` mode to actually hit the Synthscreen model.
- **Offline Support:** Includes SQLite integration and Docker configuration, making it fully ready for offline, low-resource environments.

## Integration with Other Tracks

BioLens is the practitioner surface for the full three-track ecosystem:

- **Track 1 (SynthGuard):** The sequence risk scoring engine behind the Screening page. BioLens calls it via `services/model_interface.py` — see [`docs/track1/README.md`](../track1/README.md) and [`integration_contract.md`](integration_contract.md) for the adapter spec.
- **Track 2 (Pandemic Intelligence):** Early-warning signals displayed on the Intelligence page. See [`docs/track2/README.md`](../track2/README.md) for the data format and feed architecture.

In `demo` mode, both the SynthGuard screening results and the intelligence feed run from pre-seeded local data — no external service needed.

## Directory Structure

- `app.py`: The main entry point and high-level dashboard overview.
- `pages/`: Includes specific functional sections:
  - `1_Screening.py`: The intake and evaluation workflow.
  - `2_Inbox.py`: Queue management for new cases.
  - `3_Review.py`: Deep-dive analyst investigation and decision logging.
  - `4_Analytics.py`: System-wide metrics.
  - `5_Intelligence.py`: The biosecurity threat intelligence feed.
- `services/`: Contains the core backend logic, SQLite storage handling (`storage.py`), Synthscreen integration contract (`model_interface.py`), and UI helpers (`ui.py`).
