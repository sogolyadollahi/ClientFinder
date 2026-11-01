from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .models import Lead
from .schemas import LeadCreate, LeadRead
from .scoring import calculate_score
from .source_schemas import JobOpportunityPage
from .sources.arbeitnow import ArbeitnowAdapter
from .sources.base import SourceContractError, SourceFetchError

Base.metadata.create_all(bind=engine)
app = FastAPI(title="ClientFinder API", version="0.2.0")


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
    statement = select(Lead).where(Lead.score >= min_score).order_by(Lead.score.desc()).limit(limit)
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
    """Fetch a page of public job opportunities; this does not create Lead records."""
    try:
        jobs = ArbeitnowAdapter().fetch_jobs(page=page)
    except SourceFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except SourceContractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return JobOpportunityPage(
        source="arbeitnow",
        page=page,
        count=len(jobs),
        results=jobs,
    )
