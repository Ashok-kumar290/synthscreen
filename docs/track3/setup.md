# BioLens — Setup & Usage

Instructions for running the BioLens dashboard locally or via Docker.

---

## Prerequisites

- **Python 3.11+** (tested on 3.11 and 3.14)
- **pip** (included with Python)
- **Docker** and **Docker Compose** (optional, for containerized deployment)

---

## Local Setup

### 1. Clone the repository and switch to the dashboard branch

```bash
git clone <repository-url>
cd funcscreen
git checkout dash/biolens
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Launch the dashboard

```bash
streamlit run app.py
```

The dashboard opens at **http://localhost:8501** by default.

### 5. Load demo data (optional)

Click **Load Demo Cases** in the sidebar, or set the runtime mode to `demo` before launching:

```bash
BIOLENS_MODE=demo streamlit run app.py
```

---

## Docker Setup

### Build and run

```bash
docker compose up --build
```

The dashboard is available at **http://localhost:8501**.

### Change runtime mode

```bash
BIOLENS_MODE=demo docker compose up --build
```

### Persist data across restarts

SQLite data is automatically persisted in a Docker volume (`biolens_data`). The database file is stored at `/app/data/biolens.db` inside the container.

### Stop the container

```bash
docker compose down
```

---

## Runtime Modes

BioLens supports three modes controlled by the `BIOLENS_MODE` environment variable:

| Mode | Value | Description |
|------|-------|-------------|
| **Mock** | `mock` (default) | Returns deterministic local adapter responses. No external dependency. |
| **Demo** | `demo` | Same as mock, but auto-loads representative seed cases on startup. |
| **Integrated** | `integrated` | Forwards screening requests to a live Synthscreen endpoint. |

### Integrated mode configuration

When `BIOLENS_MODE=integrated`, the following environment variables are used:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SYNTHSCREEN_ENDPOINT` | Yes | — | Full URL of the Synthscreen inference API |
| `SYNTHSCREEN_TIMEOUT_SECONDS` | No | `15` | HTTP request timeout in seconds |

Example:

```bash
BIOLENS_MODE=integrated \
SYNTHSCREEN_ENDPOINT=http://localhost:5000/screen \
streamlit run app.py
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `BIOLENS_MODE` | `mock` | Runtime mode: `mock`, `demo`, or `integrated` |
| `BIOLENS_DB_PATH` | `data/biolens.db` | Path to the SQLite database file |
| `SYNTHSCREEN_ENDPOINT` | — | Synthscreen API URL (integrated mode only) |
| `SYNTHSCREEN_TIMEOUT_SECONDS` | `15` | Request timeout (integrated mode only) |

---

## Page Overview

| Page | URL Path | Description |
|------|----------|-------------|
| **Home** | `/` | Dashboard overview with metrics, recent cases, and workflow summary |
| **Screening** | `/Screening` | Submit sequences (paste or FASTA upload), run screening, save results |
| **Inbox** | `/Inbox` | Filter, sort, and browse the case queue. Route cases to review. |
| **Review** | `/Review` | Inspect individual cases, update analyst status/notes/action, view audit trail |
| **Analytics** | `/Analytics` | Operational charts: risk distribution, status, activity timeline, top categories |

---

## Export

Cases can be exported from multiple locations:

- **Sidebar** (Home page): Download all cases as CSV or JSON
- **Inbox page**: Download the currently filtered subset
- **Review page**: Download an individual case with its audit trail

Exported files include all screening fields plus the full audit log.

---

## Project Structure

```
funcscreen/
├── app.py                    # Streamlit entry point (Home page)
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container image definition
├── docker-compose.yml        # Compose orchestration
├── .gitignore
├── pages/
│   ├── 1_Screening.py        # Sequence intake and screening
│   ├── 2_Inbox.py            # Case queue with filters
│   ├── 3_Review.py           # Case detail and analyst decision
│   └── 4_Analytics.py        # Operational metrics and charts
├── services/
│   ├── __init__.py            # Bootstrap and runtime mode
│   ├── constants.py           # Enums, paths, style tokens
│   ├── model_interface.py     # Synthscreen adapter (mock / integrated)
│   ├── storage.py             # SQLite schema and CRUD
│   ├── export.py              # CSV / JSON export
│   ├── seed_data.py           # Demo case loader
│   └── ui.py                  # Shared Streamlit styling and components
├── data/
│   └── demo_cases.json        # Representative seed cases
├── docs/
│   ├── interactive_docs.html  # Generated doc viewer (run generate_docs.py)
│   └── track3/                # Track 3 documentation (merge-safe)
│       ├── biolens_plan_v1.md
│       ├── biolens_plan_v1.1.md
│       ├── biolens_plan_v1.2.md
│       ├── setup.md           # This file
│       └── integration_contract.md
├── scripts/
│   └── generate_docs.py       # Regenerate interactive_docs.html
└── temp/                      # Local scratch (gitignored)
```

---

## Regenerating Interactive Documentation

The `docs/interactive_docs.html` file is auto-generated from all `.md` files in the repository (excluding `temp/`). It is gitignored.

To regenerate after adding or editing documentation:

```bash
python3 scripts/generate_docs.py
```

Then open `docs/interactive_docs.html` in a browser for a unified doc viewer.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `streamlit: command not found` | Activate the virtual environment: `source .venv/bin/activate` |
| Port 8501 already in use | Use `streamlit run app.py --server.port=8502` |
| Database not initializing | Check `BIOLENS_DB_PATH` and ensure the parent directory exists |
| Docker build fails | Ensure Docker daemon is running and `requirements.txt` is present |
| Interactive docs empty | Run `python3 scripts/generate_docs.py` from the repo root |
