# SynthGuard & BioLens: Unified Biosecurity Screening

> A function-aware ML screening engine (Track 1) + practitioner dashboard with pandemic intelligence (Track 3) — built for the AIxBio Hackathon 2026.

**[Live Demo](https://huggingface.co/spaces/Seyomi/biolens-dashboard)** &nbsp;|&nbsp; **[Full Report](report/funcscreen-report.md)** &nbsp;|&nbsp; **[Submission](docs/hackathon-submission.md)**

---

## The Problem

Current biosecurity screening has two critical gaps:

1. **AI-designed protein variants** share dangerous function but evade similarity-based detection (BLAST, IBBIS)
2. **Short-sequence false positives** inflate manual review cost, slowing analysts on legitimate samples

BioLens + SynthGuard address both — with a complementary ML triage layer and a unified operator workflow.

---

## Performance (Track 1 — SynthGuard)

| Metric | SynthGuard | BLAST Baseline |
|--------|:----------:|:--------------:|
| Hazard Detection — Novel Variants | **98%** | ~62% |
| Chimeric Sequence Resistance | **86%** | 48% |
| AI-Redesigned Sequence Detection | **84%** | ~41% |

---

## Architecture

```
  DNA / Protein Sequence Input
           │
           ▼
  ┌────────────────────┐
  │  SynthGuard        │  Track 1 — ESM-2 650M + LoRA (protein)
  │  Screening Engine  │           K-mer Random Forest (DNA)
  └────────┬───────────┘
           │  risk score + evidence
           ▼
  ┌────────────────────┐
  │  BioLens           │  Track 3 — Streamlit dashboard
  │  Dashboard         │           SQLite case management
  │  ┌──────────────┐  │           Audit trail + export
  │  │ Intelligence │  │
  │  │ Feed (T2)    │  │  Track 2 — Outbreak alerts, watchlists,
  │  └──────────────┘  │           regulatory updates
  └────────────────────┘
```

---

## Judge Demo Path

| Step | Page | What to see |
|------|------|-------------|
| 1 | **Home** | Global threat posture, live activity feed, regional risk map |
| 2 | **Screening** | Paste a sequence → risk score, evidence, residue highlights |
| 3 | **Inbox → Review** | Triage case, update status, log analyst decision |
| 4 | **Analytics** | Hazard distribution, response time charts, queue metrics |
| 5 | **Intelligence** | Active outbreak alerts, watchlist hits, policy updates |

---

## Quick Start

```bash
# Docker (recommended — no setup needed)
docker compose up --build
# → open http://localhost:8501

# Local (Python 3.11+)
pip install -r requirements.txt
streamlit run app.py
```

Set `BIOLENS_MODE=demo` to pre-seed all cases and intelligence data (default in Docker).

---

## Repository Structure

```
funcscreen/
├── app.py                    # BioLens entry point (home dashboard)
├── pages/                    # 8 Streamlit pages (Screening → Reports)
├── services/                 # Backend: storage, intelligence, export, model adapter
├── data/                     # SQLite DB, demo cases, intelligence feeds
├── scripts/
│   └── generate_docs.py      # Generates interactive_docs.html from all .md files
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

Full documentation (track docs, training scripts, research report) lives on the `main` branch.

---

## Branch Mapping

| Branch | Contents |
|--------|----------|
| **`main`** | Canonical showcase — BioLens dashboard + all track assets. **Start here for judging.** |
| `biolens` | Track 2 + Track 3 development history |
| `synthguard` | Track 1 model development history |

---

## Documentation

Full documentation is on the `main` branch:

- `docs/track1/README.md` — SynthGuard model architecture, metrics, training quick-start
- `docs/track2/README.md` — Pandemic intelligence layer and data format
- `docs/track3/README.md` — BioLens dashboard features and integration contract
- `report/funcscreen-report.md` — Full technical research report
