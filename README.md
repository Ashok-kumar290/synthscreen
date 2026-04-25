# BioLens — Biosecurity Screening Dashboard

**BioLens** is the Track 3 operator dashboard built on top of the Synthscreen (Track 1) DNA/protein screening engine. It provides a unified triage, review, analytics, and intelligence surface for biosecurity analysts.

## Run locally

```bash
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501) after the container starts.

## Demo path

1. **Home** — review the threat posture banner and activity feed
2. **Screening** — paste a DNA/protein sequence and run the adapter
3. **Review** — select the saved case, update analyst status, export
4. **Analytics** — verify risk distribution and response-time charts
5. **Intelligence** — inspect watchlist matches and active alerts

## Mode flags

| Variable | Values | Default | Effect |
|---|---|---|---|
| `BIOLENS_MODE` | `offline` / `online` | `offline` | Screening engine: local heuristic vs. live SynthGuard API |
| `BIOLENS_UI_MODE` | `compact` / `full` | `compact` | Sidebar nav: 5-page demo path vs. all 9 pages |
| `SYNTHSCREEN_ENDPOINT` | URL | HuggingFace space | SynthGuard API base URL (online mode only) |
| `SYNTHSCREEN_TIMEOUT_SECONDS` | number | `15` | API call timeout |

Toggle the UI mode from the floating chip (top-right) or the sidebar radio.

## Architecture note

The research report is the canonical hackathon submission. This dashboard is the supporting artifact that demonstrates the Track 3 operator workflow on top of the Track 1 model engine.
