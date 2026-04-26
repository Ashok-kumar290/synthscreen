# BioLens — AIxBio Hackathon (Track 2 + Track 3)

**Live demo:** [huggingface.co/spaces/Seyomi/biolens-dashboard](https://huggingface.co/spaces/Seyomi/biolens-dashboard)

**Branch:** `biolens` — frozen snapshot of the Track 2 and Track 3 implementation.
**Related branches:** `master` (Track 1: SynthGuard screening engine), `main` (combined showcase).

---

## Overview

BioLens is the practitioner-facing biosecurity dashboard built for the AIxBio 2026 hackathon. It represents two of the three project tracks:

| Track | Name | Description | Branch |
|-------|------|-------------|--------|
| Track 1 | **SynthGuard** | ESM-2 + LoRA protein screening engine and k-mer DNA triage model | `master` |
| Track 2 | **Pandemic Intelligence Layer** | Threat intelligence feed, watchlist management, and early-warning alerts | this branch |
| Track 3 | **BioLens Dashboard** | Streamlit operator interface for sequence intake, triage, review, analytics, automation, and compliance export | this branch |

The three tracks integrate through a single stable interface defined in `services/model_interface.py` (see [Track 1 Integration Contract](#track-1-integration-contract)).

---

## Track 2: Pandemic Intelligence Layer

### Purpose

Track 2 provides contextual awareness for biosecurity analysts. It surfaces outbreak signals, watchlist hits, regulatory updates, and research flags that inform how new sequences should be interpreted. During active high-severity alerts, screening sensitivity is raised for sequences in affected pathogen families.

### What it monitors

| Signal Type | Description |
|-------------|-------------|
| `OUTBREAK_SIGNAL` | Emerging biosecurity incidents and novel pathogen detections |
| `SURVEILLANCE_ANOMALY` | Wastewater, air sampling, or wildlife anomalies |
| `POLICY_UPDATE` | WHO, CDC, IAEA guideline and threshold changes |
| `RESEARCH_SIGNAL` | High-risk preprints, gain-of-function research flags |
| `SCREENING_RELEVANCE` | Direct cross-references from active screening results |

### Data sources

- `data/demo_intelligence.json` — Pre-seeded demo alerts for offline and judging use
- `data/intel_feed.json` — Live intelligence feed slot (populated in production)
- `services/intelligence.py` — Aggregation, deduplication, severity scoring, watchlist management

### Alert schema

Each alert record contains:

```json
{
  "id": "ALERT-001",
  "title": "Respiratory outbreak signal — Southeast Asia",
  "summary": "Unusual clustering of respiratory illness...",
  "source_type": "PUBLIC_HEALTH",
  "source_name": "WHO Disease Outbreak News",
  "signal_type": "OUTBREAK_SIGNAL",
  "severity": "MEDIUM",
  "region": "Southeast Asia",
  "timestamp": "2025-01-15T08:30:00Z",
  "status": "NEW",
  "related_pathogens": ["H5N1", "Influenza A"]
}
```

**Severity levels:** `LOW` · `MEDIUM` · `HIGH`  
**Source types:** `PUBLIC_HEALTH` · `NEWS` · `RESEARCH` · `POLICY` · `SURVEILLANCE` · `MOCK`  
**Alert statuses:** `NEW` · `REVIEWED` · `WATCHLISTED` · `DISMISSED`

### Integration with Track 3

- Active `HIGH`-severity alerts automatically raise review sensitivity for sequences matching related pathogen families
- Case-alert linkages are tracked in the `case_intelligence_links` table
- Alert statistics (active count, high-severity count, watchlist hits) appear on the Analytics and Home dashboards

### Track 2 limitations

- **No live scraping** — the intelligence feed is static JSON; no real-time polling or API integration to external sources
- **Demo data only in offline mode** — `demo_intelligence.json` contains hand-crafted representative signals, not real incident data
- **No deduplication across runs** — restarting the app re-seeds demo alerts; production would need idempotent upsert logic
- **No push notifications** — alerts surface in the UI only; no email, Slack, or webhook delivery

---

## Track 3: BioLens Operator Dashboard

### Purpose

BioLens gives biosecurity analysts a full case-management workflow on top of the SynthGuard screening engine. Analysts can screen sequences, triage flagged cases, record decisions, track operational metrics, manage automation rules, and export audit-ready compliance reports — all from a single Streamlit application that runs entirely offline.

### Application pages

| File | Page | Purpose |
|------|------|---------|
| `app.py` | **Home** | Global threat posture banner, 5 KPI cards, live activity feed, regional threat map, response-time chart, workflow guide |
| `pages/1_Screening.py` | **Screening** | Sequence intake (paste or FASTA upload); hazard score, risk tier, evidence breakdown; case auto-saved to queue |
| `pages/2_Inbox.py` | **Inbox** | Filterable case queue (by risk level, analyst status); bulk status updates; per-case quick actions |
| `pages/3_Review.py` | **Review** | Deep-dive investigation: radar chart, risk drivers, threat breakdown; analyst notes; final action; full audit trail |
| `pages/4_Analytics.py` | **Analytics** | Risk distribution, status distribution, activity-over-time, top categories, response-time histogram, alert stats |
| `pages/5_Intelligence.py` | **Intelligence** | Active alert feed, watchlist management, alert timeline, severity filter, alert statistics |
| `pages/6_Archive.py` | **Archive** | Closed and cleared cases; historical record browsing |
| `pages/7_Automation.py` | **Automation** | Create/edit auto-escalation rules; automation log; rule fire counts; enable/disable rules |
| `pages/8_Reports.py` | **Reports** | Export case histories and audit trails as CSV or JSON; date-range filtering |

**Compact mode** (default): Home · Screening · Inbox · Review  
**Full mode**: all 9 pages above

### Analyst workflow

```
Sequence submitted
      │
      ▼
  [Screening] ─── hazard score + risk tier assigned ──► case saved to DB
      │
      ▼
  [Inbox] ──── analyst picks up case (status: NEW → IN_REVIEW)
      │
      ▼
  [Review] ─── deep investigation, notes recorded
      │
      ├── ESCALATED (needs senior review or external notification)
      ├── CLEARED (safe to proceed, no further action)
      └── CLOSED (final action recorded: APPROVE · MANUAL_REVIEW · ESCALATE · HOLD)
```

**Analyst statuses:** `NEW` → `IN_REVIEW` → `ESCALATED` → `CLEARED` → `CLOSED`  
**Final actions:** `APPROVE` · `MANUAL_REVIEW` · `ESCALATE` · `HOLD`  
**Risk levels:** `SAFE` · `REVIEW` · `HIGH`

### Automation rules engine

Supervisors define rules that fire automatically when a new case is created:

| Field | Values |
|-------|--------|
| `trigger_priority` | `LOW` · `MEDIUM` · `HIGH` (watchlist match priority) |
| `trigger_severity` | `LOW` · `MEDIUM` · `HIGH` (active alert severity) |
| `action` | `AUTO_ESCALATE` · `FLAG_FOR_REVIEW` · `NOTIFY_SUPERVISOR` |

Rules evaluate on every screen submission. Matched rules update the case analyst status immediately and log the match reason to `automation_log`.

### Service layer

| Module | Role |
|--------|------|
| `services/model_interface.py` | Track 1 integration — single entry point for all screening calls |
| `services/storage.py` | SQLite persistence — all CRUD, analytics queries, audit log writes |
| `services/intelligence.py` | Alert aggregation, deduplication, watchlist management |
| `services/automation.py` | Rule engine, rule CRUD, automation log, `init_automation_tables()` |
| `services/dashboard.py` | Threat posture computation, activity feed assembly, KPI snapshots |
| `services/export.py` | `export_screenings_csv()`, `export_screenings_json()`, `build_export_dataset()` |
| `services/ui.py` | Reusable Streamlit widgets, risk badge rendering, dark-mode CSS injection |
| `services/sidebar.py` | Global navigation, mode badge, analyst/supervisor role toggle |
| `services/constants.py` | Enums, style maps, page lists for compact/full UI modes |
| `services/seed_data.py` | Demo case and alert initialisation for offline mode |

### Database schema

```
screenings
  id, submitted_at, reviewed_at
  sequence_text, sequence_type
  hazard_score, risk_level, confidence
  category, explanation, baseline_result
  model_name, data_source
  analyst_status, analyst_notes, final_action
  threat_breakdown (JSON), attribution_data (JSON)

audit_log
  screening_id → screenings.id
  event_type, event_time, details (JSON)

intelligence_alerts
  id, title, summary
  source_type, source_name, signal_type
  severity, region, timestamp, status
  related_pathogens (JSON)

watchlist_items
  id, name, category, priority
  added_at, notes

case_intelligence_links
  screening_id → screenings.id
  alert_id → intelligence_alerts.id
  link_type, linked_at

automation_rules
  id, name, description
  trigger_priority, trigger_severity
  action, target_status
  enabled, created_by, created_at, fire_count

automation_log
  rule_id → automation_rules.id
  rule_name, case_id, action_taken
  match_reason, fired_at
```

### Track 3 limitations

- **No real authentication** — the Analyst / Supervisor role toggle in the sidebar is UI-only; there is no session management or access control
- **Single-user SQLite** — the database does not support concurrent multi-analyst access; concurrent writes will cause contention
- **Sequence attribution is illustrative** — in offline mode, the residue-level highlighting is placeholder logic, not real attribution from the model
- **Radar chart dimensions are heuristic** — Toxicity / Pathogenicity / Environmental Risk values are derived from hazard score + category, not separate model outputs
- **No notification delivery** — `NOTIFY_SUPERVISOR` automation action sets a flag in the log; no email, webhook, or push is sent
- **Docker is single-container** — no orchestration or horizontal scaling; the persistent volume is local to one host
- **No sequence deduplication** — the same sequence can be submitted multiple times and creates duplicate cases

---

## Track 1 Integration Contract

All SynthGuard calls flow through one function in one module:

```python
# services/model_interface.py
def screen_sequence(sequence: str, seq_type: str) -> dict:
```

### Parameters

| Parameter | Type | Values |
|-----------|------|--------|
| `sequence` | `str` | Raw nucleotide or amino acid string (whitespace stripped, uppercased internally) |
| `seq_type` | `str` | `"DNA"` or `"PROTEIN"` |

### Return schema

```python
{
    "ok": bool,                    # True = success, False = error
    "hazard_score": float | None,  # 0.0–1.0 normalised
    "risk_level": str | None,      # "SAFE" | "REVIEW" | "HIGH"
    "confidence": float | None,    # 0.0–1.0 normalised
    "category": str | None,        # Predicted functional category label
    "explanation": str | None,     # Short readable reasoning
    "baseline_result": str | None, # Optional baseline comparison text
    "model_name": str,             # Audit identifier
    "data_source": str,            # "synthguard-api" | "biolens-offline"
    "error": str | None            # Machine-readable error when ok=False
}
```

### Dual-engine behaviour

| Mode | DNA sequences | Protein sequences |
|------|--------------|-------------------|
| `online` | POST to `SYNTHSCREEN_ENDPOINT` (SynthGuard API) | Local BioLens heuristic (API is DNA-only) |
| `offline` | Local BioLens heuristic | Local BioLens heuristic |

### Offline heuristic

The offline heuristic is **not a real ML model**. It uses a deterministic hash of the input sequence to generate a reproducible hazard score and category label. Its sole purpose is to allow the full UI workflow to run without a GPU or API dependency. Results are meaningless from a biosecurity perspective.

### Validation rules

- DNA alphabet: `A C G T N`
- Protein alphabet: `A B C D E F G H I K L M N P Q R S T V W X Y Z *`
- Max sequence length: 50 KB
- Common error codes: `empty_sequence_input`, `invalid_dna_characters:<chars>`, `integration_timeout_error`, `integration_connection_error`

### Default API endpoint

```
https://seyomi-synthguard-api.hf.space/biolens/screen
```

Override with `SYNTHSCREEN_ENDPOINT` env var.

---

## Quick Start

### Live demo (HuggingFace Space)

[https://huggingface.co/spaces/Seyomi/biolens-dashboard](https://huggingface.co/spaces/Seyomi/biolens-dashboard)

Runs in `online` mode against the SynthGuard API. No installation required.

### Docker (recommended)

```bash
docker compose up --build
```

Opens at [http://localhost:8501](http://localhost:8501) in `offline` mode with pre-seeded demo data.

### Local Python (3.11+)

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Environment variables

| Variable | Default | Values | Effect |
|----------|---------|--------|--------|
| `BIOLENS_MODE` | `offline` | `offline` / `online` | Screening engine: local heuristic vs. SynthGuard API |
| `BIOLENS_UI_MODE` | `compact` | `compact` / `full` | Sidebar nav: 4-page demo path vs. all 9 pages |
| `SYNTHSCREEN_ENDPOINT` | `https://seyomi-synthguard-api.hf.space/biolens/screen` | Any URL | SynthGuard API base URL (online mode only) |
| `SYNTHSCREEN_TIMEOUT_SECONDS` | `30` | Number | API call timeout in seconds |
| `BIOLENS_DB_PATH` | `/app/data/biolens.db` | File path | SQLite database location |

The UI mode can also be toggled at runtime via the sidebar without restarting.

---

## Demo Walkthrough

1. **Home** — check the threat posture banner, activity feed, and KPI cards
2. **Screening** — paste a sequence and click Screen; observe hazard score and risk tier
   - Sample DNA: `ATGAAAGCAATTTTCGTACTGAAAGGTTTTGTTGGTTTTCTTGCATTTTTTTATAATGTT`
   - Sample protein: `MKALFILGLLFCFATAAADYKDDDDKGIPLEFSKDLDKYAQYTLNRDRGFHIGDKLISAL`
3. **Inbox** — find the newly created case in the queue; open it
4. **Review** — examine the radar chart and risk drivers; record analyst notes; set a final action
5. **Analytics** — verify the risk distribution and response-time charts updated
6. **Intelligence** — browse active alerts and watchlist entries; check severity breakdown

---

## Repository Structure

```
funcscreen/
├── app.py                        # Home dashboard (Track 3 entry point)
├── pages/
│   ├── 1_Screening.py            # Sequence intake and triage
│   ├── 2_Inbox.py                # Case queue management
│   ├── 3_Review.py               # Deep-dive analyst workflow
│   ├── 4_Analytics.py            # Operational metrics
│   ├── 5_Intelligence.py         # Biosecurity alerts and watchlist (Track 2)
│   ├── 6_Archive.py              # Closed cases
│   ├── 7_Automation.py           # Auto-escalation rule management
│   └── 8_Reports.py              # Export and compliance reports
├── services/
│   ├── __init__.py               # App bootstrap, runtime mode init
│   ├── constants.py              # Enums, style maps, page lists
│   ├── storage.py                # SQLite CRUD, analytics queries
│   ├── model_interface.py        # Track 1 integration contract
│   ├── intelligence.py           # Track 2 alert aggregation
│   ├── automation.py             # Automation rule engine
│   ├── dashboard.py              # Threat posture, activity feed
│   ├── export.py                 # CSV/JSON export utilities
│   ├── sidebar.py                # Navigation and role toggle
│   ├── ui.py                     # Streamlit widgets and CSS
│   └── seed_data.py              # Demo data initialisation
├── data/
│   ├── biolens.db                # SQLite database (runtime, gitignored)
│   ├── demo_cases.json           # Pre-seeded demo screenings
│   ├── demo_intelligence.json    # Pre-seeded demo alerts (Track 2)
│   ├── intel_feed.json           # Live intelligence feed slot
│   └── sample_dataset.json       # Example sequences for testing
├── scripts/
│   └── generate_docs.py          # Builds docs/interactive_docs.html from all .md files (output gitignored)
├── Dockerfile                    # Python 3.11-slim Streamlit container
├── docker-compose.yml            # Single-service orchestration with persistent volume
├── requirements.txt              # streamlit, plotly, pandas
├── .dockerignore
├── .gitignore
└── README.md                     # This file
```

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| UI framework | Streamlit ≥ 1.32 |
| Visualisation | Plotly ≥ 6.0 |
| Data processing | Pandas ≥ 2.2 |
| Persistence | SQLite 3 |
| Container | Docker (Python 3.11-slim) |
| Track 1 API | HTTP/JSON (urllib) |
