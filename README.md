# SynthGuard & BioLens: Unified Biosecurity Screening

This repository contains the full submission for the Biosecurity Hackathon. Our project addresses the critical need for robust, scalable, and intelligent biosecurity screening to prevent the synthesis of potentially hazardous biological agents.

## Project Overview

Our solution is a multi-track integration that spans from low-level sequence screening to high-level pandemic intelligence and operator triage.

### Track 1: SynthGuard DNA/Protein Screening Backend
- **Core Engine**: A high-performance screening backend that evaluates DNA and protein sequences against known pathogen databases and functional signatures.
- **Model Work**: Implements advanced sequence alignment and functional annotation to detect "de-novo" or modified sequences that traditional tools might miss.
- **Branch**: `master` (contains the core backend and model logic).

### Track 2: Early Pandemic Intelligence Signals
- **Intelligence Layer**: Aggregates early signals of pandemic potential from global health data, watchlists, and environmental monitoring.
- **Integration**: These signals are fed directly into the BioLens dashboard to provide operators with real-time situational awareness.
- **Implementation**: Integrated into the `Intelligence` module of the dashboard.

### Track 3: BioLens Unified Biosecurity Dashboard
- **Operator Surface**: A Streamlit-based unified dashboard for biosecurity analysts.
- **Features**: Triage sequences, review automated alerts, analyze global risk trends, and manage pandemic intelligence signals.
- **Branch**: `main` (Showcase) / `track3/biolens`.

## Branch Mapping

- **`main`**: The canonical showcase branch. Contains the runnable BioLens dashboard and project overview. **(Start here for judging)**
- **`track3/biolens`**: Permanent branch for Track 3 implementation and dashboard development.
- **`master`**: Track 1 backend and model development branch.

## Quick Start (Local Demo)

The entire BioLens dashboard, including integrated Track 1 and Track 2 features, can be run locally using Docker:

```bash
docker compose up --build
```

Access the dashboard at [http://localhost:8501](http://localhost:8501).

---

## Documentation

- [Hackathon Submission Detailed Report](docs/hackathon-submission.md)
- [Track 3 Detailed Documentation](docs/track3/README.md)
