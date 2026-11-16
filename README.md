# Event Sync Service

A take-home assessment implementation using **Python, FastAPI and Streamlit**. It ingests CRM and Calendar JSON files, reconciles likely meeting matches, preserves source lineage, and exposes conflicts for review.

## Architecture

- `backend/app/ingestion.py`: defensive JSON ingestion and record-level validation.
- `backend/app/reconciliation.py`: normalization, date parsing, weighted candidate scoring, one-to-one matching, conflict detection, provenance and duplicate review.
- `backend/app/main.py`: FastAPI REST API.
- `frontend/streamlit_app.py`: dashboard with search, filters, source details and conflict review.
- `tests/`: unit and API tests.

## Requirements

Python 3.11 or newer recommended.

## Setup

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

Start the API from the project root:

```bash
uvicorn backend.app.main:app --reload --port 8000
```

In a second terminal:

```bash
streamlit run frontend/streamlit_app.py
```

Open:
- Streamlit UI: http://localhost:8501
- Swagger API docs: http://localhost:8000/docs
- API health: http://localhost:8000/health

## API endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/meetings` | Unified meeting list; supports `q`, `source`, `status`, `has_conflicts` |
| GET | `/api/meetings/{meeting_id}` | One meeting with raw records and provenance |
| GET | `/api/meetings/conflicts` | Meetings with field conflicts |
| GET | `/api/meetings/review` | Potential matches below auto-match threshold |
| GET | `/api/meetings/duplicates` | Possible same-source duplicate pairs |
| GET | `/api/meetings/stats` | Dashboard metrics |
| GET | `/api/sync/errors` | Ingestion errors |
| POST | `/api/sync` | Reload files and rebuild reconciliation |

## Reconciliation approach

Candidate records must have the same normalized calendar date. A weighted score is then calculated:

| Signal | Weight |
|---|---:|
| Client/company or attendee evidence | 30% |
| Same date | 25% |
| Title similarity | 20% |
| Start-time proximity | 17% |
| Location similarity | 8% |

- `>= 0.68`: automatic match.
- `0.50–0.6799`: candidate sent to review; records remain separate.
- `< 0.50`: no match.
- Internal meetings receive a small explicit context bonus only when date, start time and location all align; this helps reconcile shorthand internal titles without broadening client-meeting matching.
- One CRM record can match at most one Calendar record.
- A source-only record is retained in the unified list.
- Conflicting values are never silently overwritten; the selected display value and both original values are available in `provenance` and `conflicts`.
- Suspected duplicates are flagged for review, not deleted automatically.

### Timezone assumption

The input contains both timezone-aware timestamps (for example, a `Z` suffix) and timezone-naive values. The implementation compares wall-clock values and gives a reduced time score for differences up to six hours. This is an explicit pragmatic assumption for the sample data, not a universal timezone conversion rule. A production service should require or configure each source's timezone and normalize all timestamps to UTC.

### Recurrence

Each calendar event row is treated as an occurrence. Recurring events on different dates are not collapsed into one event. The recurrence flag is retained for display.

### Duplicate policy

Potential same-source duplicates are surfaced for review. Similar meetings can be legitimate separate meetings, so the system does not destructively delete them.

## Run tests

```bash
pytest -q
```

## Design trade-offs and production improvements

1. Persist raw and reconciled records in PostgreSQL/SQLite instead of rebuilding from JSON on each process start.
2. Add source adapters with retry, timeout, pagination and incremental sync checkpoints when replacing local JSON with upstream APIs.
3. Store match decisions and allow a user to confirm/reject candidate pairs.
4. Replace the sample wall-clock timezone assumption with configured source timezones.
5. Add idempotency keys, audit history, structured logs, metrics and authentication.
6. Tune score weights and thresholds using labeled match/non-match examples; do not treat the illustrative weights as statistically calibrated.
