# Track-2-Inspired Intelligence Layer

The intelligence layer gives BioLens analysts situational awareness alongside sequence screening. It is Track-2-inspired support for the Track 3 dashboard, not a full submitted Track 2 pandemic early-warning system. The current prototype uses demo/operator-curated alerts, watchlists, and triage modifiers rather than live external surveillance ingestion.

---

## What It Monitors

| Signal Category | Description |
|----------------|-------------|
| **Global Alerts** | Emerging biosecurity incidents, novel pathogen detections, outbreak reports |
| **Watchlist Hits** | Sequence or entity matches against curated dual-use research watchlists |
| **Regulatory Updates** | Policy changes from WHO, CDC, IAEA affecting screening thresholds |
| **Research Signals** | High-risk preprint publications and gain-of-function research flags |
| **Environmental Feeds** | Environmental monitoring anomalies (wastewater, air sampling, wildlife reports) |

---

## Architecture

```
intel_feed.json / demo_intelligence.json
        │
        ▼
services/intelligence.py  ←─ aggregation + deduplication + severity scoring
        │
        ▼
pages/5_Intelligence.py   ←─ BioLens Intelligence dashboard page
```

- **`services/intelligence.py`**: Loads, deduplicates, and severity-scores alerts from the intelligence data sources.
- **`data/intel_feed.json`**: Reserved future feed slot for production external intelligence integration.
- **`data/demo_intelligence.json`**: Pre-seeded demo signals for offline showcase/judging.
- **`pages/5_Intelligence.py`**: Streamlit page rendering the feed, with filtering by severity, category, and date.

---

## Integration with Screening (Track 1)

Intelligence signals influence operational triage in the BioLens Screening page. When an active watchlist item matches a screening result, BioLens records the raw model output, the intelligence modifier, and the adjusted operational score used by the analyst workflow.

---

## Data Format

Each intelligence signal follows this structure:

```json
{
  "id": "INTEL-2024-0047",
  "timestamp": "2024-11-15T08:30:00Z",
  "category": "outbreak_alert",
  "severity": "high",
  "title": "Novel H5N1 variant detected — elevated mammalian transmission",
  "summary": "WHO reports 3 confirmed human cases in Southeast Asia...",
  "source": "WHO Disease Outbreak News",
  "related_pathogens": ["H5N1", "Influenza A"],
  "watchlist_match": false,
  "action_required": true
}
```

---

## Runtime Modes

| Mode | Intelligence Behaviour |
|------|----------------------|
| `mock` | No intelligence data; feed shows empty state |
| `demo` | Pre-seeded `demo_intelligence.json` loaded at startup |
| `integrated` | Reserved for future production external intelligence integration |

Set the runtime mode via the `BIOLENS_MODE` environment variable or the sidebar toggle in BioLens.

---

## Limitations

- **Data Freshness:** In `integrated` mode, the feed relies on periodic file updates rather than a true streaming API. Real-time streaming (e.g., ProMED, GPHIN webhook) is a planned future integration.
- **Coverage:** Current watchlists are curated snapshots; automated watchlist refresh from canonical sources (Australia Group, Wassenaar Arrangement) is not yet implemented.

---

## Future Work

- Webhook integration with ProMED and WHO Disease Outbreak News RSS feeds
- NLP-based relevance scoring to surface the highest-priority alerts automatically
- Cross-referencing intelligence alerts with active cases in the BioLens review queue
