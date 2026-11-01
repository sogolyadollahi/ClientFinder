# ClientFinder — Phase 2

A focused lead-discovery and qualification API. The project currently provides a stable lead-management foundation and its first external job-source adapter.

## Current scope
- Create leads manually.
- Validate incoming lead data.
- Normalize website URLs and reject duplicate websites.
- Score leads using transparent deterministic rules.
- List leads by minimum score and status; retrieve a lead by ID.
- Fetch and normalize public job listings from Arbeitnow through a source adapter.

## Stack
Python 3.12+, FastAPI, SQLAlchemy 2, Pydantic 2, SQLite (local development), HTTPX, Pytest.

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

## Discover public job opportunities

`GET /sources/arbeitnow/jobs?page=1`

This endpoint fetches one page from the public Arbeitnow job-board API and returns normalized job-opportunity records. It does **not** automatically create Lead rows.

Why they are separate: the job feed provides a company name and a job-posting URL, but does not reliably provide the company's canonical website. ClientFinder currently requires a company website to create a Lead and uses that website as its deduplication key. Treating a job-posting URL as the company website would corrupt the data model. A later enrichment step must verify the company's official website before promotion to Lead.

The source adapter validates the response shape and raises explicit errors for network failures or unexpected source data. It uses a 15-second request timeout.

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
- Arbeitnow listings are opportunity signals, not proof that the company wants to hire an external agency or freelancer.
- No automatic company-website enrichment yet.
- No LinkedIn scraping or automated messaging.
- No email sending.
- Public contact details must be used responsibly and in line with applicable law and source terms.
- The Arbeitnow API is provided as-is; the provider asks consumers to link back to Arbeitnow and may revoke API access.

## Planned phases
1. Data model, API, deduplication, baseline scoring (complete).
2. Source adapters for approved public sources and job/contract opportunity feeds (first adapter implemented).
3. Enrichment, evidence extraction, and improved scoring.
4. Streamlit dashboard, review queue, and outreach drafts.
5. Feedback loop: contacted / replied / call / proposal / won / lost.
