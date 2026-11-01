# ClientFinder — Phase 2

A focused lead-discovery and qualification API. It stores manually qualified company leads separately from raw job opportunities discovered through external sources.

## Current scope
- Create, list, and retrieve qualified leads.
- Validate incoming lead data and deduplicate leads by normalized company website.
- Score leads using transparent deterministic rules.
- Fetch and normalize public job listings from Arbeitnow.
- Persist opportunities independently from leads.
- Upsert opportunities by the unique pair `source + external_id`.
- Filter stored opportunities by source, remote status, location, and keyword.

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

## Run tests

```powershell
pytest -q
```

## Source discovery and persistence

Preview one page without writing to the database:

`GET /sources/arbeitnow/jobs?page=1`

Fetch and persist one page:

`POST /sources/arbeitnow/sync?page=1`

The sync endpoint returns counts for fetched, created, updated, and unchanged records. Re-running the same page is idempotent: it does not create duplicate rows. A changed listing updates the existing row.

Browse saved records:

- `GET /opportunities`
- `GET /opportunities/{opportunity_id}`

Supported filters on `GET /opportunities`:

- `source=arbeitnow`
- `remote=true` or `remote=false`
- `location=Berlin`
- `keyword=Python`
- `limit=50` (maximum 200)

Example:

`GET /opportunities?remote=true&location=Berlin&keyword=Python&limit=20`

## Data model boundary

An Opportunity is a source listing. A Lead is a company record that has enough verified company-level information to qualify for outreach. Arbeitnow provides a company name and job-posting URL, but that URL is not necessarily the company's canonical website. Therefore, syncing opportunities does not automatically create leads.

The opportunity table keeps the source's external identifier and source URL, and records when ClientFinder first and most recently observed the listing.

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
- The Arbeitnow API is provided as-is; follow its current usage terms and attribution requirements.

## Planned phases
1. Data model, API, deduplication, baseline scoring (complete).
2. Source adapters, opportunity persistence, and searchable discovery (implemented for first source).
3. Company enrichment, evidence extraction, and improved scoring.
4. Streamlit dashboard, review queue, and outreach drafts.
5. Feedback loop: contacted / replied / call / proposal / won / lost.
