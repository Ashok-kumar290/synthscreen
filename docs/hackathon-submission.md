# Hackathon Submission: BioLens & SynthGuard

## Problem Statement
Current biosecurity screening workflows are fragmented. Analysts often have to pivot between multiple tools for sequence alignment, risk assessment, and intelligence gathering. This slows down response times and increases the risk of human error in detecting hazardous synthesis requests.

## What Was Built
We built a unified biosecurity ecosystem:
1.  **SynthGuard**: A robust sequence screening engine (Track 1).
2.  **BioLens**: A comprehensive operator dashboard (Track 3) that integrates:
    *   Direct screening capabilities via SynthGuard.
    *   Pandemic intelligence signals (Track 2).
    *   Case management and analytics for oversight.

## Architecture Overview
- **Backend**: Python-based screening engine with optimized alignment algorithms.
- **Frontend**: Streamlit dashboard for rapid prototyping and interactive data visualization.
- **Data Layers**: Integrated watchlists, pathogen databases, and real-time intelligence feeds.
- **Containerization**: Docker-ready for consistent deployment.

## Demo Path
1.  **Home**: Overview of current global threat posture.
2.  **Screening**: Test a sequence (DNA/Protein) against the engine.
3.  **Review**: Manage triage cases and update status.
4.  **Analytics**: View system-wide performance and risk metrics.
5.  **Intelligence**: Monitor early warning signals and watchlist hits.

## Limitations
- **Scaling**: Heuristic screening is optimized for speed but requires high-memory instances for very large databases.
- **Data Freshness**: Intelligence signals currently rely on periodic updates rather than true real-time streaming for some sources.

## Future Work
- **AI-Assisted Triage**: Implementing LLM-based summaries for screening results to aid analysts.
- **Cloud Native**: Moving to a serverless architecture for the screening backend to handle bursty workloads.
- **Wider Integrations**: Connecting to more global health monitoring APIs.
