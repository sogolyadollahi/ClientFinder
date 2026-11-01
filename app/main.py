from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .enrichment import build_company_candidates
from .models import Lead, Opportunity
from .schemas import LeadCreate, LeadRead
from .scoring import calculate_score
from .source_schemas import (
    CompanyCandidate,
    JobOpportunityPage,
    OpportunityRead,
    OpportunitySyncResult,
)
from .sources.arbeitnow import ArbeitnowAdapter
from .sources.base import SourceContractError, SourceFetchError

Base.metadata.create_all(bind=engine)
app = FastAPI(title="ClientFinder API", version="0.4.0")


@app.get("/health")
def health():
    return {"status": "ok", "service": "clientfinder"}


@app.post("/leads", response_model=LeadRead, status_code=201)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    website = str(payload.website).rstrip("/").lower()
    existing = db.scalar(select(Lead).where(Lead.website == website))
    if existing:
        raise HTTPException(status_code=409, detail="A lead with this website already exists")

    result = calculate_score(
        services_text=payload.services_text,
        evidence_text=payload.evidence_text,
        company_size=payload.company_size,
        has_public_contact=bool(payload.public_contact),
    )
    lead = Lead(
        company_name=payload.company_name.strip(),
        website=website,
        region=payload.region,
        company_size=payload.company_size,
        opportunity_types=payload.opportunity_types,
        services_text=payload.services_text,
        evidence_text=payload.evidence_text,
        public_contact=str(payload.public_contact) if payload.public_contact else None,
        score=result.score,
        score_reasons="; ".join(result.reasons),
    )
    db.add(lead)
    try:
        db.commit()
        db.refresh(lead)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A lead with this website already exists")
    return lead


@app.get("/leads", response_model=list[LeadRead])
def list_leads(
    min_score: int = Query(default=0, ge=0, le=100),
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    statement = (
        select(Lead)
        .where(Lead.score >= min_score)
        .order_by(Lead.score.desc())
        .limit(limit)
    )
    if status:
        statement = statement.where(Lead.status == status)
    return list(db.scalars(statement).all())


@app.get("/leads/{lead_id}", response_model=LeadRead)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.get("/sources/arbeitnow/jobs", response_model=JobOpportunityPage)
def discover_arbeitnow_jobs(page: int = Query(default=1, ge=1, le=100)):
    """Fetch and preview one page; this endpoint does not write to the database."""
    try:
        jobs = ArbeitnowAdapter().fetch_jobs(page=page)
    except SourceFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SourceContractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return JobOpportunityPage(source="arbeitnow", page=page, count=len(jobs), results=jobs)


@app.post("/sources/arbeitnow/sync", response_model=OpportunitySyncResult)
def sync_arbeitnow_jobs(
    page: int = Query(default=1, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Fetch one page and upsert opportunities using source + external ID."""
    try:
        jobs = ArbeitnowAdapter().fetch_jobs(page=page)
    except SourceFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SourceContractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    created = updated = unchanged = 0
    now = datetime.now(timezone.utc)

    try:
        for job in jobs:
            values = {
                "company_name": job.company_name,
                "title": job.title,
                "location": job.location,
                "remote": job.remote,
                "tags": job.tags,
                "job_types": job.job_types,
                "description": job.description,
                "source_url": str(job.source_url),
                "source_created_at": job.created_at,
            }
            existing = db.scalar(
                select(Opportunity).where(
                    Opportunity.source == job.source,
                    Opportunity.external_id == job.external_id,
                )
            )
            if existing is None:
                db.add(
                    Opportunity(
                        source=job.source,
                        external_id=job.external_id,
                        **values,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                created += 1
                continue

            changed = any(getattr(existing, key) != value for key, value in values.items())
            existing.last_seen_at = now
            if changed:
                for key, value in values.items():
                    setattr(existing, key, value)
                updated += 1
            else:
                unchanged += 1

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An opportunity was inserted concurrently; retry the sync",
        ) from exc

    return OpportunitySyncResult(
        source="arbeitnow",
        fetched=len(jobs),
        created=created,
        updated=updated,
        unchanged=unchanged,
    )


@app.get("/opportunities", response_model=list[OpportunityRead])
def list_opportunities(
    source: str | None = None,
    remote: bool | None = None,
    location: str | None = Query(default=None, max_length=200),
    keyword: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    statement = select(Opportunity)
    if source:
        statement = statement.where(Opportunity.source == source)
    if remote is not None:
        statement = statement.where(Opportunity.remote.is_(remote))
    if location:
        statement = statement.where(Opportunity.location.ilike(f"%{location}%"))
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                Opportunity.title.ilike(pattern),
                Opportunity.company_name.ilike(pattern),
                Opportunity.description.ilike(pattern),
            )
        )
    statement = statement.order_by(Opportunity.source_created_at.desc()).limit(limit)
    return list(db.scalars(statement).all())


@app.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)):
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunity


@app.get("/companies/candidates", response_model=list[CompanyCandidate])
def list_company_candidates(
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Aggregate job signals into reviewable company candidates; does not create Leads."""
    records = db.scalars(select(Opportunity).order_by(Opportunity.company_name)).all()
    candidates = build_company_candidates(records)
    filtered = [item for item in candidates if item["qualification_score"] >= min_score]
    return filtered[:limit]
