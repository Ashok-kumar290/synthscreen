# BioLens — AIxBio Hackathon 2026

**Live demo:** [huggingface.co/spaces/Seyomi/biolens-dashboard](https://huggingface.co/spaces/Seyomi/biolens-dashboard)

BioLens is a practitioner-facing biosecurity dashboard built for the [AIxBio Hackathon 2026](https://apartresearch.com/sprints/aixbio-hackathon-2026-04-24-to-2026-04-26) (April 24–26, hosted by Apart Research). It addresses a gap identified in the hackathon's Track 3 brief: biosecurity analysts have no unified operational surface. Screening engines, threat intelligence, outbreak signals, and compliance workflows exist in silos — BioLens connects them into a single triage-to-report workflow that runs entirely offline or against a live AI screening API.

The project covers three of the four hackathon tracks. Track 1 (the SynthGuard screening engine) is on a separate branch (`synthguard`) and is the work of a teammate. Tracks 2 and 3 are on this branch.

---

## Tracks

| # | Track | Sponsor | What we built | Branch |
|---|-------|---------|---------------|--------|
| 1 | **DNA Screening & Synthesis Controls** | CBAI | ESM-2 + LoRA protein hazard scoring; k-mer DNA triage model | `synthguard` |
| 2 | **Pandemic Early Warning** | Measuring AI Progress | Threat intelligence feed, outbreak signal aggregation, watchlist engine | `biolens` |
| 3 | **AI Biosecurity Tools** | Fourth Eon Bio | BioLens: full analyst workflow — intake, triage, review, analytics, automation, compliance export | `biolens` |

All three tracks integrate through a single stable interface in `services/model_interface.py` (see [Track 1 Integration Contract](#track-1-integration-contract)).

---

## Track 2: Pandemic Intelligence Layer

### What it does

The intelligence layer gives analysts real-time situational awareness alongside sequence screening. It aggregates outbreak signals, surveillance anomalies, policy changes, and high-risk research flags into a unified alert feed. When a `HIGH`-severity alert is active, the dashboard surfaces it prominently and raises analyst review sensitivity for sequences in related pathogen families — closing the gap between surveillance signals and lab screening decisions.

### Signal types

| Signal Type | Description |
|-------------|-------------|
| `OUTBREAK_SIGNAL` | Emerging biosecurity incidents and novel pathogen detections |
| `SURVEILLANCE_ANOMALY` | Wastewater, air sampling, or wildlife anomalies |
| `POLICY_UPDATE` | WHO, CDC, IAEA guideline and threshold changes |
| `RESEARCH_SIGNAL` | High-risk preprints, gain-of-function research flags |
| `SCREENING_RELEVANCE` | Direct cross-references from active screening results |

### Data sources

- `data/demo_intelligence.json` — pre-seeded demo alerts for offline and judging use
- `data/intel_feed.json` — live intelligence feed slot (populated in production)
- `services/intelligence.py` — aggregation, deduplication, severity scoring, watchlist management

### Alert schema

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

### Cross-track integration

- Active `HIGH`-severity alerts raise review sensitivity for sequences matching related pathogen families
- Case-alert linkages are tracked in the `case_intelligence_links` SQLite table
- Alert stats (active count, high-severity count, watchlist hits) feed the Analytics and Home dashboards

### Limitations

- **No live scraping** — the intelligence feed is static JSON; no real-time polling or external API integration
- **Demo data only** — `demo_intelligence.json` contains hand-crafted representative signals, not real incident data
- **No deduplication across runs** — restarting re-seeds demo alerts; production would need idempotent upsert logic
- **No push notifications** — alerts surface in the UI only; no email, Slack, or webhook delivery

---

## Track 3: BioLens Operator Dashboard

### What it does

BioLens gives biosecurity analysts a complete case-management workflow on top of the SynthGuard screening engine. A sequence submitted on the Screening page flows automatically through risk scoring, into the analyst inbox, through a structured review and decision process, and finally into audit-ready compliance exports — all without leaving a single Streamlit application that runs entirely offline.

### Application pages

| File | Page | Purpose |
|------|------|---------|
| `app.py` | **Home** | Global threat posture banner, 5 KPI cards, live activity feed, regional threat map, response-time chart |
| `pages/1_Screening.py` | **Screening** | Sequence intake (paste or FASTA upload); hazard score, risk tier, threat breakdown; case auto-saved to queue |
| `pages/2_Inbox.py` | **Inbox** | Filterable case queue (by risk level, analyst status); bulk status updates; per-case quick actions |
| `pages/3_Review.py` | **Review** | Deep-dive investigation: radar chart, risk drivers, analyst notes, final action, full audit trail |
| `pages/4_Analytics.py` | **Analytics** | Risk distribution, status distribution, activity-over-time, top categories, response-time histogram, alert stats |
| `pages/5_Intelligence.py` | **Intelligence** | Active alert feed, watchlist management, alert timeline, severity filter, alert statistics |
| `pages/6_Archive.py` | **Archive** | Closed and cleared cases; historical record browsing |
| `pages/7_Automation.py` | **Automation** | Create/edit auto-escalation rules; automation log; rule fire counts; enable/disable |
| `pages/8_Reports.py` | **Reports** | Export case histories and audit trails as CSV or JSON; date-range filtering |

**Compact mode** (default): Home · Screening · Inbox · Review  
**Full mode**: all 9 pages above

### Analyst workflow

```
Sequence submitted
      │
      ▼
  [Screening] ── hazard score + risk tier assigned ──► case saved to DB
      │
      ▼
  [Inbox] ──── analyst picks up case (NEW → IN_REVIEW)
      │
      ▼
  [Review] ─── deep investigation, notes recorded
      │
      ├── ESCALATED  (needs senior review or external notification)
      ├── CLEARED    (safe to proceed, no further action)
      └── CLOSED     (final action: APPROVE · MANUAL_REVIEW · ESCALATE · HOLD)
```

**Analyst statuses:** `NEW` → `IN_REVIEW` → `ESCALATED` → `CLEARED` → `CLOSED`  
**Risk levels:** `SAFE` · `REVIEW` · `HIGH`

### Automation rules engine

Supervisors define rules that fire automatically on every new case:

| Field | Values |
|-------|--------|
| `trigger_priority` | `LOW` · `MEDIUM` · `HIGH` (watchlist match priority) |
| `trigger_severity` | `LOW` · `MEDIUM` · `HIGH` (active alert severity) |
| `action` | `AUTO_ESCALATE` · `FLAG_FOR_REVIEW` · `NOTIFY_SUPERVISOR` |

Matched rules update the case analyst status immediately and log the match reason to `automation_log`.

### Service layer

| Module | Role |
|--------|------|
| `services/model_interface.py` | Track 1 integration — sole entry point for all screening calls |
| `services/storage.py` | SQLite persistence — all CRUD, analytics queries, audit log writes |
| `services/intelligence.py` | Alert aggregation, deduplication, watchlist management |
| `services/automation.py` | Rule engine, rule CRUD, automation log |
| `services/dashboard.py` | Threat posture computation, activity feed assembly, KPI snapshots |
| `services/export.py` | `export_screenings_csv()`, `export_screenings_json()`, `build_export_dataset()` |
| `services/ui.py` | Reusable Streamlit widgets, risk badge rendering, dark-mode CSS |
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

### Limitations

- **No real authentication** — the Analyst / Supervisor toggle is UI-only; no session management or access control
- **Single-user SQLite** — concurrent multi-analyst writes will cause contention
- **Sequence attribution is illustrative** — in offline mode, residue-level highlighting uses heuristic logic, not real model attribution
- **Radar chart dimensions are heuristic** — Pathogenicity / Evasion / Synthesis Feasibility / Environmental Resilience / Host Range are derived from the offline heuristic, not separate model outputs
- **No notification delivery** — `NOTIFY_SUPERVISOR` logs the action; no email, webhook, or push is sent
- **Docker is single-container** — no orchestration or horizontal scaling
- **No sequence deduplication** — the same sequence can be submitted multiple times

---

## Track 1 Integration Contract

All SynthGuard calls flow through one function:

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
    "threat_breakdown": dict | None, # pathogenicity, evasion_potential, synthesis_feasibility,
                                     # environmental_resilience, host_range (0.0–1.0 each)
    "attribution_data": dict | None, # residue positions and scores for highlight rendering
    "error": str | None            # Machine-readable error when ok=False
}
```

### Dual-engine behaviour

| Mode | DNA | Protein |
|------|-----|---------|
| `online` | POST `/biolens/screen` on SynthGuard API | POST `/biolens/screen` on SynthGuard API |
| `offline` | BioLens built-in heuristic | BioLens built-in heuristic |

### Offline heuristic

The offline heuristic is **not a real ML model**. For DNA it combines GC content deviation, motif density (`ATG`, `TATA`, `CGCG`, `GGG`), repeat runs, and N-fraction with a deterministic hash of the sequence to produce a reproducible hazard score. For protein it uses hydrophobic/charged amino acid fractions, low-complexity, and motif density (`KK`, `RR`, `KR`, `GP`, `GG`). Its sole purpose is to let the full UI workflow run without a network connection or GPU. Scores are meaningless from a real biosecurity perspective.

### Validation

- DNA alphabet: `A C G T N`
- Protein alphabet: `A B C D E F G H I K L M N P Q R S T V W X Y Z *`
- Max sequence length: 50 KB
- Short sequences (<20 bp/aa) trigger an elevated-uncertainty note in the explanation field
- Common error codes: `empty_sequence_input`, `invalid_dna_characters:<chars>`, `api_timeout`, `api_http_error:<code>`, `api_connection_error:<reason>`

### Default API endpoint

```
https://seyomi-synthguard-api.hf.space/biolens/screen
```

Override with the `SYNTHSCREEN_ENDPOINT` env var.

---

## Quick Start

### Live demo (HuggingFace Space)

[https://huggingface.co/spaces/Seyomi/biolens-dashboard](https://huggingface.co/spaces/Seyomi/biolens-dashboard)

Runs in `online` mode against the SynthGuard API. No installation required.

### Docker (recommended for local use)

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
| `SYNTHSCREEN_TIMEOUT_SECONDS` | `15` | Number | API call timeout in seconds |
| `BIOLENS_DB_PATH` | `/app/data/biolens.db` | File path | SQLite database location |

The UI mode can also be toggled at runtime via the sidebar without restarting.

---

## Demo Walkthrough

1. **Home** — review the threat posture banner, KPI cards, and live activity feed
2. **Screening** — paste a sequence and click Screen; observe hazard score, risk tier, and threat breakdown
   - Sample DNA: `ATGAAAGCAATTTTCGTACTGAAAGGTTTTGTTGGTTTTCTTGCATTTTTTTATAATGTT`
   - Sample protein: `MKALFILGLLFCFATAAADYKDDDDKGIPLEFSKDLDKYAQYTLNRDRGFHIGDKLISAL`
3. **Inbox** — find the newly created case in the queue
4. **Review** — examine the radar chart and risk drivers; record analyst notes; set a final action
5. **Analytics** — verify the risk distribution and response-time charts updated
6. **Intelligence** — browse active alerts and watchlist entries

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
│   └── 8_Reports.py              # Compliance export
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
│   └── generate_docs.py          # Generates docs/interactive_docs.html from all .md files (output gitignored)
├── Dockerfile                    # Python 3.11-slim Streamlit container
├── docker-compose.yml            # Single-service orchestration with persistent volume
├── requirements.txt              # streamlit, plotly, pandas
├── .dockerignore
├── .gitignore
└── README.md
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
| Track 1 API | HTTP/JSON (urllib, stdlib only) |
