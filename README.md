# ClientFinder — Phase 3

A focused lead-discovery and qualification API. It stores manually qualified company leads separately from raw job opportunities discovered through external sources.

## Current scope
- Create, list, and retrieve qualified leads.
- Validate incoming lead data and deduplicate leads by normalized company website.
- Score manually qualified leads using transparent deterministic rules.
- Fetch and normalize public job listings from Arbeitnow.
- Persist opportunities independently from leads and upsert by `source + external_id`.
- Filter stored opportunities by source, remote status, location, and keyword.
- Aggregate opportunities into company candidates using conservative name normalization.
- Extract technical skills and hiring signals with deterministic keyword rules.
- Return explainable candidate scores and evidence without automatically creating Leads.

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

Re-running the same page is idempotent. Browse saved records:

- `GET /opportunities`
- `GET /opportunities/{opportunity_id}`

Filters on `GET /opportunities`: `source`, `remote`, `location`, `keyword`, and `limit`.

## Company candidate enrichment

`GET /companies/candidates`

Optional query parameters:
- `min_score=30`: minimum heuristic qualification score (0–100).
- `limit=50`: maximum number of company candidates returned (1–200).

The endpoint groups stored opportunities by a normalized company-name key, then aggregates:
- Detected technical skills (keyword taxonomy).
- Technical-role, multiple-opening, remote-hiring, and external-work-language signals.
- Evidence snippets and score reasons.
- Opportunity IDs, role titles, locations, and remote listing count.

The score is a transparent prioritization heuristic, not a probability of conversion or proof of agency demand. The current normalizer strips common legal suffixes; it does not resolve legal entities, subsidiaries, or similarly named companies. Keyword matches can produce false positives and require human review.

**Important:** Company candidates are not Leads. The endpoint does not guess official websites, discover personal contact data, or create Lead records. A candidate should be promoted only after a person verifies the company's official website and relevant company-level evidence.

## Data model boundary

- `Opportunity`: a source job listing, identified by `source + external_id`.
- `Company candidate`: a computed aggregation of one or more opportunities, not a persisted legal-entity record.
- `Lead`: a manually qualified company record with a verified website and reviewed evidence.

An Arbeitnow job-posting URL is not treated as the company's official website.

## Scoring model

Company-candidate score (0–100) is additive and explainable:
- Technical skills detected: up to 30.
- Multiple listings: 15.
- Technical roles: 15.
- Remote hiring: 10.
- Explicit contract/freelance/agency language: 20.
- Three or more listings: 10.

This score ranks candidates for manual review. Job listings are weak-to-moderate buying signals; they do not establish that the company wants an external agency or freelancer.

The separate Lead score remains the existing baseline and should be calibrated against actual outreach outcomes.

## Limitations and safety
- One source page is synced per request.
- No automatic official-website discovery or validation yet.
- No LinkedIn scraping, automated messaging, or email sending.
- Job descriptions are stored as source text; any future UI must escape/sanitize HTML before rendering.
- Follow the source provider's current usage terms and attribution requirements.

## Planned phases
1. Data model, API, deduplication, baseline scoring (complete).
2. Source adapters, opportunity persistence, and searchable discovery (implemented for Arbeitnow).
3. Company candidate aggregation, evidence extraction, and explainable prioritization (implemented baseline).
4. Streamlit dashboard, review queue, and outreach drafts.
5. Feedback loop: contacted / replied / call / proposal / won / lost.
