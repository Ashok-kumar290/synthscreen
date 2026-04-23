# BioLens

**Operational dashboard for function-aware biosecurity screening**

## Status

Draft v1.1

## Purpose

BioLens is the Track 3 operational layer for a function-aware biological sequence screening system. It is designed to transform screening outputs into a usable review workflow for biosecurity practitioners, synthesis providers, and laboratory safety teams.

BioLens is not a standalone screening engine. It is the interface and workflow layer that sits on top of Synthscreen (Track 1) and enables practical use through sequence intake, triage, review, analytics, and reporting.

## Project Positioning

This project is positioned as:

- **Primary contribution:** Synthscreen (Track 1) -- function-aware sequence screening
- **Supporting product layer:** BioLens (Track 3) -- practitioner-facing dashboard and workflow tooling

The complete system should be framed as a deployable biosecurity screening workflow rather than only a standalone model or only a dashboard.

## Problem Statement

Function-aware screening systems can improve detection of hazardous or evasive biological sequences, including cases that may be poorly handled by conventional similarity-based approaches. However, model output alone is not sufficient for operational use.

A deployable screening workflow requires:

- a clear intake mechanism for sequences
- triage of model outputs into actionable categories
- a review interface for flagged cases
- a way to record analyst decisions
- persistent audit logs and analytics
- structured report generation

BioLens addresses this gap between model inference and operational decision-making.

## Assumptions

The current plan assumes the following:

- Synthscreen remains the authoritative Track 1 screening system.
- BioLens consumes Synthscreen outputs through a single adapter interface.
- Early development uses mock inference responses until Synthscreen integration is available.
- SQLite is sufficient for hackathon scope and local/demo use.
- The initial operating mode is single-user and local-first.
- Deployment-grade security, authentication, and distributed infrastructure are outside the current scope.

## Scope

BioLens covers the practitioner workflow around screening results.

### In scope

- sequence submission and intake
- screening result display
- flagged case queue / inbox
- case review workflow
- analyst decision recording
- audit logging
- operational analytics
- exportable reports
- integration with Synthscreen through a stable interface contract

### Out of scope

- model training or fine-tuning
- large-scale backend infrastructure
- live multi-source threat intelligence aggregation
- enterprise authentication / authorization
- policy scraping across jurisdictions
- adversarial sequence generation
- replacing the Synthscreen screening engine

## High-Level Workflow

```text
Intake --> Screening --> Triage --> Review --> Decision --> Reporting
```

1. **Intake**
   A sequence is submitted through text input or FASTA upload.

2. **Screening**
   The dashboard calls the Synthscreen screening interface and receives a structured result.

3. **Triage**
   The result is assigned to an operational risk tier such as `SAFE`, `REVIEW`, or `HIGH`.

4. **Review**
   Flagged cases are stored and surfaced in a review queue for inspection.

5. **Decision**
   A reviewer records status, notes, and a final action.

6. **Reporting**
   Case data and review history are persisted and can be exported as structured reports.

## Run Modes

BioLens should support three operational modes during development and integration.

### 1. Mock Mode

Used during early development.

- `model_interface.py` returns hardcoded responses
- no dependency on Synthscreen runtime
- used for initial page development and workflow testing

### 2. Seeded Demo Mode

Used for demos, screenshots, and walkthroughs.

- preloaded representative cases are inserted into SQLite
- inbox, analytics, and review flows are populated without requiring live inference
- useful for judge-facing demos and local testing

### 3. Integrated Mode

Used after Synthscreen integration is available.

- `model_interface.py` calls real Synthscreen inference
- live screening results are stored and reviewed through the same workflow
- seeded demo cases may still be retained for demonstration purposes

## Core Features

### 1. Screening Page

Primary entry point for sequence submission.

Capabilities:

- paste sequence input
- single or batch FASTA upload
- DNA / protein selection
- execution of the screening interface
- display of:
  - risk level
  - risk score
  - confidence
  - category
  - explanation
  - optional baseline comparison
- save result to case inbox

### 2. Case Inbox

Operational queue of saved screening results.

Capabilities:

- list all cases
- filter by analyst status
- sort by risk score or timestamp
- color-coded risk display
- navigation into detailed review view

Suggested statuses:

- `NEW`
- `IN_REVIEW`
- `ESCALATED`
- `CLEARED`
- `CLOSED`

### 3. Case Review Page

Detailed case inspection and decision interface.

Capabilities:

- display sequence metadata
- display model result and explanation
- show optional baseline / BLAST comparison
- record reviewer status
- record final action
- add analyst notes
- show audit trail for case events

Suggested final actions:

- `APPROVE`
- `MANUAL_REVIEW`
- `ESCALATE`
- `HOLD`

### 4. Analytics Dashboard

Operational metrics derived from persisted cases.

Capabilities:

- total sequences screened
- total flagged
- flagged rate
- risk distribution
- activity over time
- top flagged categories
- status distribution

### 5. Export and Reporting

Structured case export for review and documentation.

Priority outputs:

- CSV export
- JSON export

Stretch output:

- PDF report

Suggested report contents:

- case identifier
- timestamps
- sequence type
- screening result
- explanation
- reviewer status
- final action
- notes

## System Architecture

```text
┌──────────────────────────────────────────────┐
│                   BioLens                    │
│   Screening / Inbox / Review / Analytics    │
└───────────────────────┬──────────────────────┘
                        │
                ┌───────┴────────┐
                │ SQLite Storage │
                │ cases + audit  │
                └───────┬────────┘
                        │
                ┌───────┴──────────────┐
                │ model_interface.py   │
                │ adapter layer        │
                └───────┬──────────────┘
                        │
                ┌───────┴──────────────┐
                │ Synthscreen           │
                │ screening interface  │
                └──────────────────────┘
```

## Integration Strategy

BioLens should be developed independently of unfinished Synthscreen implementation details. Integration should happen through a single adapter layer.

### Design rule

Only one module should need to change during Synthscreen integration:

- `model_interface.py`

All other parts of BioLens should remain unchanged.

### Development mode

During early development, `model_interface.py` returns mock responses.

### Integration mode

When Synthscreen inference is available, the mock implementation is replaced by a real inference call while preserving the same output contract.

## Model Interface Contract

The Synthscreen integration must conform to a stable interface.

```python
def screen_sequence(sequence: str, seq_type: str) -> dict:
    """
    Args:
        sequence: raw DNA or protein sequence
        seq_type: "DNA" or "PROTEIN"

    Returns:
        {
            "ok": bool,
            "hazard_score": float | None,
            "risk_level": str | None,       # SAFE | REVIEW | HIGH
            "confidence": float | None,
            "category": str | None,
            "explanation": str | None,
            "baseline_result": str | None,
            "model_name": str,
            "error": str | None
        }
    """
```

### Contract notes

- `hazard_score` should be normalized to the range `0.0` to `1.0`.
- `risk_level` should be one of `SAFE`, `REVIEW`, or `HIGH`.
- `seq_type` should be one of `DNA` or `PROTEIN`.
- `confidence` should be normalized to the range `0.0` to `1.0`.
- `explanation` should be short, readable, and appropriate for operator workflows.
- `baseline_result` is optional and can be omitted until baseline comparison is available.
- `model_name` is included for auditability and debugging.
- `ok=False` indicates that inference failed or the request was invalid.
- `error` should contain a short machine-readable or human-readable failure reason when `ok=False`.

## Error Handling

BioLens should fail safely and predictably.

### Expected error cases

- empty sequence input
- invalid FASTA upload
- unsupported sequence type
- malformed or non-biological input
- model inference failure
- database insert/update failure
- export failure

### Expected behavior

- errors should be surfaced clearly in the UI
- invalid inputs should not create screening cases
- inference failures should not be written as completed screenings
- database errors should be logged and surfaced to the operator
- export errors should not corrupt stored case data

## Data Storage

BioLens should use a lightweight SQLite database for persistence.

### Table: `screenings`

| Field           | Type        | Notes                         |
| --------------- | ----------- | ----------------------------- |
| id              | TEXT (UUID) | Primary key                   |
| submitted_at    | TIMESTAMP   | Auto-set on insert            |
| sequence_text   | TEXT        | Raw input sequence            |
| sequence_type   | TEXT        | "DNA" or "PROTEIN"            |
| hazard_score    | REAL        | 0.0 to 1.0                    |
| risk_level      | TEXT        | SAFE / REVIEW / HIGH          |
| confidence      | REAL        | 0.0 to 1.0                    |
| category        | TEXT        | Predicted functional category |
| explanation     | TEXT        | Model reasoning               |
| baseline_result | TEXT        | Nullable, optional            |
| model_name      | TEXT        | Model identifier              |
| analyst_status  | TEXT        | Default "NEW"                 |
| analyst_notes   | TEXT        | Nullable                      |
| final_action    | TEXT        | Nullable                      |
| reviewed_at     | TIMESTAMP   | Nullable                      |

### Table: `audit_log`

| Field        | Type      | Notes                              |
| ------------ | --------- | ---------------------------------- |
| id           | INTEGER   | Auto-increment primary key         |
| screening_id | TEXT (FK) | References screenings.id           |
| event_type   | TEXT      | e.g. "status_change", "action_set" |
| event_time   | TIMESTAMP | Auto-set                           |
| details      | TEXT      | JSON string with change details    |

## Technology Choices

Suggested implementation stack:

- **UI:** Streamlit
- **Storage:** SQLite
- **Application logic:** Python
- **Export:** standard CSV / JSON libraries
- **PDF stretch option:** `fpdf2` or `reportlab`
- **Sequence parsing:** Biopython or a lightweight FASTA parser

This stack is intentionally simple to optimize for development speed, portability, and later integration.

## Repository Structure

Suggested structure for the Track 3 branch or module:

```text
app.py
requirements.txt
README.md
pages/
  1_Screening.py
  2_Inbox.py
  3_Review.py
  4_Analytics.py
services/
  model_interface.py
  storage.py
  export.py
  seed_data.py
data/
  biolens.db
  demo_cases.json
docs/
  integration_contract.md
  biolens_plan.md
```

## Merge and Portability Notes

BioLens is intended to be developed in a modular way so it can later be merged into the main repository with minimal changes.

Design constraints:

- avoid direct imports from unfinished Synthscreen internals
- keep model-specific assumptions isolated to `model_interface.py`
- avoid hardcoding final merged repo paths
- keep storage and export logic independent of Synthscreen implementation details
- preserve portability of `pages/`, `services/`, and `docs/`

## Demo Strategy

BioLens should remain demoable even before Synthscreen integration is complete.

### Seed data

Preload a small set of representative cases:

- safe cases
- review-level cases
- high-risk cases
- mixed analyst statuses

### Preferred walkthrough

A judge or reviewer should be able to:

1. submit a sequence
2. observe a flagged result
3. open the case inbox
4. review a case
5. record a decision
6. export a report

This should work end-to-end in development mode using mock responses.

## Stretch Feature

### Baseline / BLAST comparison panel

If time permits, add a side-by-side comparison on the case review page showing:

- conventional similarity-based output
- function-aware model output
- a concise explanation of where the function-aware approach adds value

This should only be implemented after the five core features are complete.

## Safety and Dual-Use Constraints

BioLens is a defensive biosecurity workflow tool.

The implementation should follow these constraints:

- no sequence generation or optimization features
- no evasion assistance or screening bypass guidance
- no workflow that increases offensive capability
- no detailed explanatory content that instructs misuse
- demo cases and examples should be selected to avoid enabling harm

This constraint applies to application behavior, seed data, documentation, and presentation materials.

## Non-Goals

To preserve scope discipline, BioLens should explicitly avoid the following:

- becoming a general "VirusTotal for bio" platform
- becoming a live policy intelligence system
- becoming a multi-user enterprise product
- implementing heavy backend services
- implementing sequence generation or red-team tooling

The project should stay tightly scoped around operationalizing Synthscreen screening.

## Implementation Phases

### Phase 0 -- Foundation

Work:

- application skeleton
- mock model interface
- SQLite schema
- basic navigation

Definition of done:

- app launches locally
- SQLite schema initializes successfully
- mock mode returns valid contract responses
- navigation between pages works

### Phase 1 -- Screening

Work:

- input UI
- model call
- result rendering
- save case flow

Definition of done:

- a sequence can be submitted in mock mode
- a screening result renders successfully
- a valid result can be saved as a case

### Phase 2 -- Inbox

Work:

- case list
- filtering
- sorting
- navigation to detail view

Definition of done:

- saved cases appear in inbox
- filtering and sorting work
- clicking a case opens the review page

### Phase 3 -- Review

Work:

- detailed case display
- analyst status updates
- notes
- final action
- audit trail

Definition of done:

- a case can be reviewed and updated
- changes are persisted
- audit entries are created and displayed

### Phase 4 -- Analytics

Work:

- basic operational metrics
- charts from SQLite data

Definition of done:

- analytics read from persisted data
- key metrics render without manual intervention

### Phase 5 -- Export

Work:

- CSV export
- JSON export
- optional PDF stretch

Definition of done:

- at least one case export path works end-to-end
- exported content matches stored case data

### Phase 6 -- Integration

Work:

- swap mock inference for Synthscreen inference
- validate field mappings
- test representative cases
- update demo cases with real outputs

Definition of done:

- integrated mode returns valid contract responses
- mock and integrated modes remain switchable if needed
- integration requires changes only in the adapter layer

## Acceptance Criteria

BioLens is considered functionally complete when all of the following are true:

- sequences can be submitted and screened
- results can be saved as cases
- cases appear in an inbox
- cases can be reviewed and updated
- audit history is stored
- analytics render from persisted data
- at least one export path works
- Synthscreen integration requires changing only the model adapter layer

## Final Positioning Statement

BioLens is the operational dashboard built on top of the Synthscreen screening engine. The combined system should be presented as a complete biosecurity screening workflow:

- **Synthscreen (Track 1):** function-aware sequence screening and detection
- **BioLens (Track 3):** practitioner workflow for review, triage, analytics, and reporting

Together, these components form a deployable screening system rather than only a model or only a dashboard.

## See Also

- Synthscreen repository and documentation (Track 1)
- AIxBio Hackathon 2026 submission guidelines
