# ClientFinder — Phase 7

A focused lead-discovery and qualification API. It keeps raw job opportunities, computed company candidates, manual company verification, and qualified Leads as separate stages.

## Current scope
- Create, list, and retrieve qualified company leads.
- Fetch and persist public job listings from Arbeitnow.
- Deduplicate source listings and filter saved opportunities.
- Aggregate opportunities into company candidates with deterministic skill and hiring-signal extraction.
- Maintain a persistent manual company-review queue.
- Require a manually verified official website before promoting a candidate to a Lead.
- Record Lead interactions and maintain a sales-pipeline status.
- Store personalized outreach drafts based on saved research facts and user-provided context.
- Report Lead, interaction, and draft counts by pipeline stage.
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

Install the optional dashboard dependencies with `pip install -e ".[dashboard]"`.

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

No automatic domain guessing or website discovery is performed. A human must verify that the website belongs to the company. The system does not scrape LinkedIn, collect personal contact data, send email, or automate outreach. Outreach endpoints only save drafts; a human must review and send them outside the system.

## Scoring and evidence

Candidate scoring is a prioritization heuristic. Lead promotion recalculates the existing Lead score from detected skills and stored evidence. The score is not a conversion probability. Job listings alone do not prove that a company needs an external agency or freelancer.

## Known limitations
- Company grouping is based on normalized names, not legal entity resolution.
- Website verification is a human attestation recorded by the API; the service does not independently prove domain ownership.
- SQLite `create_all` is used for local development; introduce Alembic migrations before deploying schema changes to an existing production database.
- Job description content must be escaped/sanitized before rendering in any UI.


## Phase 5 — Outreach and pipeline

- Record an interaction: `POST /leads/{lead_id}/interactions`
  - Allowed types: `contacted`, `replied`, `call`, `proposal`, `won`, `lost`.
  - Optional fields: notes, occurrence timestamp, and next-action timestamp.
  - The Lead's current status reflects the most recently recorded interaction.
- List interaction history: `GET /leads/{lead_id}/interactions`
- Create an outreach draft: `POST /leads/{lead_id}/outreach-drafts`
  - Example JSON: `{"channel":"email","tone":"professional","context":"Optional user-written context"}`
  - Channels: email, LinkedIn, or other. Tones: professional or concise.
- List drafts: `GET /leads/{lead_id}/outreach-drafts`
- Pipeline summary: `GET /analytics/pipeline`

Draft generation uses only saved Lead research fields and optional user-provided context. It does not verify claims, discover contacts, or send messages. Review and edit every draft before using it. Interactions are append-only history records; the Lead status is a convenient current-stage field, not a replacement for that history.


## Phase 6 — Streamlit dashboard

Start the API in one terminal:

```powershell
uvicorn app.main:app --reload
```

Install dashboard dependencies and start the UI in a second terminal:

```powershell
pip install -e ".[dashboard]"
streamlit run dashboard/streamlit_app.py
```

Open the local Streamlit URL shown in the terminal (usually http://localhost:8501). The dashboard reads and writes data through the FastAPI service; it does not access the database directly.

Set CLIENTFINDER_API_URL if the API is hosted somewhere other than http://127.0.0.1:8000. The dashboard includes:
- Overview metrics for Leads, pipeline stages, interactions, drafts, and saved opportunities.
- Lead filtering by pipeline stage and minimum score.
- Lead detail, research evidence, and interaction history.
- Interaction logging with optional next-action timestamp.
- Email / LinkedIn / other outreach draft creation and review. Drafts are never sent.
- Arbeitnow opportunity browsing and manual source sync.

The dashboard is intended for trusted local use. The API currently has no authentication; do not expose either service publicly without adding authentication, authorization, and deployment hardening.


## Phase 7 — Dynamic discovery

### Company discovery — Exa

ClientFinder uses Exa Search API for live company discovery.

- Endpoint: `POST /discovery/companies/search`
- Search type: `lite`
- Category: `company`
- Returned fields: result title, URL, highlights, location context, and a deterministic fit score.
- Exa results are displayed in the dashboard for the current session. They are **not persisted** in the ClientFinder database while the provider's output-storage permission remains unconfirmed.
- A result title may be a page title rather than the legal company name. Verify the company and official domain independently before creating a Lead.

Configure the Exa key in the FastAPI server environment only:

```powershell
$env:EXA_API_KEY = "your-exa-api-key"
uvicorn app.main:app --reload
```

Do not put API keys in Streamlit, frontend code, GitHub, or committed configuration files.

Check current quotas and pricing at https://exa.ai/pricing/ and the API reference at https://exa.ai/docs/reference/search.

### Job and contract discovery

The structured live Google Jobs integration remains on SerpApi and requires a separate `SERPAPI_API_KEY`. Arbeitnow remains available as a supplementary source.

```powershell
$env:SERPAPI_API_KEY = "your-serpapi-key"
```

Do not assume Exa's company search endpoint is a structured replacement for Google Jobs. The Exa integration currently covers company discovery only.

### Dashboard

- Company discovery: live Exa search with session-only results.
- Company verification: existing manual verification workflow for records already in the review queue.
- Jobs: live SerpApi job search plus Arbeitnow sync.

### Data boundaries

- Exa search results are not persisted.
- Company titles and highlights are research signals, not proof of company identity, official-domain ownership, or purchase intent.
- The fit score is keyword-based prioritization, not a probability.
- Keep the API local/private; the API has no authentication.
