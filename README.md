# ClientFinder — Phase 4

A focused lead-discovery and qualification API. It keeps raw job opportunities, computed company candidates, manual company verification, and qualified Leads as separate stages.

## Current scope
- Create, list, and retrieve qualified company leads.
- Fetch and persist public job listings from Arbeitnow.
- Deduplicate source listings and filter saved opportunities.
- Aggregate opportunities into company candidates with deterministic skill and hiring-signal extraction.
- Maintain a persistent manual company-review queue.
- Require a manually verified official website before promoting a candidate to a Lead.
- Prevent duplicate promotion of the same review and duplicate Lead website records.

## Stack
Python 3.12+, FastAPI, SQLAlchemy 2, Pydantic 2, SQLite, HTTPX, Pytest.

## Setup (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Run tests with `pytest -q`.

## Main workflow

1. Preview or sync a source page:
   - `GET /sources/arbeitnow/jobs?page=1`
   - `POST /sources/arbeitnow/sync?page=1`
2. Inspect opportunities:
   - `GET /opportunities`
3. Inspect grouped company candidates:
   - `GET /companies/candidates?min_score=30`
4. Add a candidate to the manual review queue:
   - `POST /companies/reviews`
   - JSON: `{"normalized_key":"example","company_name":"Example GmbH"}`
5. Review queue:
   - `GET /companies/reviews?status=pending`
6. Record manual verification:
   - `PATCH /companies/reviews/{review_id}`
   - JSON: `{"official_website":"https://example.com","verification_status":"verified","verification_notes":"Official site checked manually"}`
   - A website is mandatory when status is `verified`.
7. Promote a verified company:
   - `POST /companies/reviews/{review_id}/promote`
   - Creates a Lead using the stored opportunity evidence and existing deterministic Lead scoring.
   - Repeating promotion returns the same Lead instead of creating a duplicate.

A review can also be marked `rejected` or returned to `pending`. The website field is normalized to the origin (scheme + hostname), stripping `www` and URL paths before uniqueness checks.

## Data model boundaries

- `Opportunity`: source job listing.
- `Company candidate`: computed aggregation of opportunities; not proof of legal-entity identity.
- `CompanyReview`: persistent manual verification state, official website, reviewer notes, and eventual Lead reference.
- `Lead`: qualified company record eligible for later outreach preparation.

No automatic domain guessing or website discovery is performed. A human must verify that the website belongs to the company. The system does not scrape LinkedIn, collect personal contact data, send email, or automate outreach.

## Scoring and evidence

Candidate scoring is a prioritization heuristic. Lead promotion recalculates the existing Lead score from detected skills and stored evidence. The score is not a conversion probability. Job listings alone do not prove that a company needs an external agency or freelancer.

## Known limitations
- Company grouping is based on normalized names, not legal entity resolution.
- Website verification is a human attestation recorded by the API; the service does not independently prove domain ownership.
- SQLite `create_all` is used for local development; introduce Alembic migrations before deploying schema changes to an existing production database.
- Job description content must be escaped/sanitized before rendering in any UI.
