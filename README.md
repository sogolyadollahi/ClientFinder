# ClientFinder — Phase 1

A small API foundation for collecting, storing, deduplicating, and scoring agency leads.
This phase deliberately does **not** scrape websites or send outreach messages.

## Current scope
- Create leads manually or from a future approved data source.
- Validate incoming lead data.
- Normalize website URLs and reject duplicate websites.
- Score leads using transparent deterministic rules.
- List leads by minimum score and status.
- Retrieve a lead by ID.

## Stack
Python 3.12+, FastAPI, SQLAlchemy 2, Pydantic 2, SQLite (local development), Pytest.

## Setup (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open:
- API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## Run tests

```powershell
pytest -q
```

## Example lead payload

```json
{
  "company_name": "Example Automation Agency",
  "website": "https://example.com",
  "region": "Europe",
  "company_size": "small",
  "opportunity_types": "both",
  "services_text": "n8n automation, CRM, API integration and Python",
  "evidence_text": "We are hiring remote freelance developers",
  "public_contact": "hello@example.com"
}
```

Send it to `POST /leads`.

## Scoring model (v0)
- Service relevance: up to 30
- Hiring/collaboration signals: up to 25
- Company-size fit: up to 15
- Remote-work signal: up to 20
- Public business contact: up to 10

This is a heuristic baseline, not a prediction of conversion probability. The weights must be calibrated against actual outreach outcomes.

## Important limitations
- No automated web collection yet.
- No LinkedIn scraping or automated messaging.
- No email sending.
- No claim that a company accepts contractors located in every country.
- Public contact details must be used responsibly and in line with applicable law and source terms.

## Planned phases
1. Data model, API, deduplication, baseline scoring (current).
2. Source adapters for approved public sources and job/contract opportunity feeds.
3. Enrichment, evidence extraction, and improved scoring.
4. Streamlit dashboard, review queue, and outreach drafts.
5. Feedback loop: contacted / replied / call / proposal / won / lost.
