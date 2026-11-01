from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .enrichment import build_company_candidates
from .models import CompanyReview, Lead, LeadInteraction, Opportunity, OutreachDraft
from .schemas import (
    CompanyReviewCreate,
    CompanyReviewRead,
    CompanyReviewUpdate,
    LeadCreate,
    LeadPromotionResult,
    LeadRead,
    LeadInteractionCreate,
    LeadInteractionRead,
    OutreachDraftCreate,
    OutreachDraftRead,
    PipelineSummary,
)
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
app = FastAPI(title="ClientFinder API", version="0.5.0")


def canonicalize_website(url: str) -> str:
    """Store only the verified website origin; remove www and tracking paths."""
    parsed = urlsplit(str(url))
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        raise ValueError("A valid website hostname is required")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme.lower()}://{host}{port}"


def _candidate_for_key(db: Session, normalized_key: str) -> dict | None:
    records = db.scalars(select(Opportunity)).all()
    return next(
        (
            candidate
            for candidate in build_company_candidates(records)
            if candidate["normalized_key"] == normalized_key
        ),
        None,
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "clientfinder"}


@app.post("/leads", response_model=LeadRead, status_code=201)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    website = canonicalize_website(str(payload.website))
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
        public_contact=payload.public_contact,
        score=result.score,
        score_reasons="; ".join(result.reasons),
    )
    db.add(lead)
    try:
        db.commit()
        db.refresh(lead)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A lead with this website already exists") from exc
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
    except (SourceFetchError, SourceContractError) as exc:
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
    except (SourceFetchError, SourceContractError) as exc:
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
                db.add(Opportunity(
                    source=job.source, external_id=job.external_id, **values,
                    first_seen_at=now, last_seen_at=now,
                ))
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
        source="arbeitnow", fetched=len(jobs), created=created,
        updated=updated, unchanged=unchanged,
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
        statement = statement.where(or_(
            Opportunity.title.ilike(pattern),
            Opportunity.company_name.ilike(pattern),
            Opportunity.description.ilike(pattern),
        ))
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


@app.post("/companies/reviews", response_model=CompanyReviewRead, status_code=201)
def create_company_review(
    payload: CompanyReviewCreate,
    db: Session = Depends(get_db),
):
    candidate = _candidate_for_key(db, payload.normalized_key)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Company candidate not found")
    existing = db.scalar(
        select(CompanyReview).where(CompanyReview.normalized_key == payload.normalized_key)
    )
    if existing:
        return existing
    review = CompanyReview(
        normalized_key=payload.normalized_key,
        company_name=candidate["company_name"],
        verification_status="pending",
    )
    db.add(review)
    try:
        db.commit()
        db.refresh(review)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Review already exists") from exc
    return review


@app.get("/companies/reviews", response_model=list[CompanyReviewRead])
def list_company_reviews(
    status: str | None = Query(default=None, pattern="^(pending|verified|rejected)$"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    statement = select(CompanyReview).order_by(CompanyReview.updated_at.desc()).limit(limit)
    if status:
        statement = statement.where(CompanyReview.verification_status == status)
    return list(db.scalars(statement).all())


@app.patch("/companies/reviews/{review_id}", response_model=CompanyReviewRead)
def update_company_review(
    review_id: int,
    payload: CompanyReviewUpdate,
    db: Session = Depends(get_db),
):
    review = db.get(CompanyReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Company review not found")
    if payload.verification_status == "verified" and payload.official_website is None:
        raise HTTPException(
            status_code=422,
            detail="An official website is required before marking a company verified",
        )
    if payload.official_website is not None:
        review.official_website = canonicalize_website(str(payload.official_website))
    review.verification_status = payload.verification_status
    review.verification_notes = payload.verification_notes
    try:
        db.commit()
        db.refresh(review)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Website conflicts with an existing lead") from exc
    return review


@app.post("/companies/reviews/{review_id}/promote", response_model=LeadPromotionResult)
def promote_company_review(review_id: int, db: Session = Depends(get_db)):
    review = db.get(CompanyReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Company review not found")
    if review.lead_id is not None:
        lead = db.get(Lead, review.lead_id)
        if lead is not None:
            return LeadPromotionResult(review=review, lead=lead)
    if review.verification_status != "verified" or not review.official_website:
        raise HTTPException(status_code=409, detail="Verify the official website before promotion")

    candidate = _candidate_for_key(db, review.normalized_key)
    if candidate is None:
        raise HTTPException(status_code=409, detail="No current opportunity evidence for this company")

    existing = db.scalar(select(Lead).where(Lead.website == review.official_website))
    if existing:
        raise HTTPException(status_code=409, detail="A Lead already exists for this website")

    services_text = ", ".join(candidate["detected_skills"])
    evidence_text = "\n".join(candidate["evidence"] + candidate["score_reasons"])
    score = calculate_score(
        services_text=services_text,
        evidence_text=evidence_text,
        company_size="unknown",
        has_public_contact=False,
    )
    lead = Lead(
        company_name=review.company_name,
        website=review.official_website,
        region=", ".join(candidate["locations"][:3]) or "unknown",
        company_size="unknown",
        opportunity_types="both",
        services_text=services_text,
        evidence_text=evidence_text,
        public_contact=None,
        score=score.score,
        score_reasons="; ".join(score.reasons),
        status="new",
    )
    db.add(lead)
    try:
        db.flush()
        review.lead_id = lead.id
        db.commit()
        db.refresh(lead)
        db.refresh(review)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Lead promotion conflicted with an existing record") from exc
    return LeadPromotionResult(review=review, lead=lead)



@app.post("/leads/{lead_id}/interactions", response_model=LeadInteractionRead, status_code=201)
def create_lead_interaction(
    lead_id: int,
    payload: LeadInteractionCreate,
    db: Session = Depends(get_db),
):
    """Record an interaction and advance the Lead's current pipeline status."""
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    interaction = LeadInteraction(
        lead_id=lead_id,
        interaction_type=payload.interaction_type,
        notes=payload.notes,
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
        next_action_at=payload.next_action_at,
    )
    db.add(interaction)
    lead.status = payload.interaction_type
    db.commit()
    db.refresh(interaction)
    return interaction


@app.get("/leads/{lead_id}/interactions", response_model=list[LeadInteractionRead])
def list_lead_interactions(lead_id: int, db: Session = Depends(get_db)):
    if db.get(Lead, lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    statement = (
        select(LeadInteraction)
        .where(LeadInteraction.lead_id == lead_id)
        .order_by(LeadInteraction.occurred_at.desc(), LeadInteraction.id.desc())
    )
    return list(db.scalars(statement).all())


def _build_outreach_copy(lead: Lead, payload: OutreachDraftCreate) -> tuple[str, str]:
    """Build a conservative draft from stored lead facts and explicitly supplied context."""
    subject = f"Exploring potential collaboration with {lead.company_name}"
    greeting = f"Hello {lead.company_name} team,"
    if payload.tone == "concise":
        paragraphs = [
            greeting,
            "Would external technical support be useful for your team at the moment?",
        ]
        if payload.context.strip():
            paragraphs.append(payload.context.strip())
        paragraphs.append("Best regards,\n[Your name]")
    else:
        paragraphs = [
            greeting,
            "I’m reaching out to explore whether external technical support could be useful for your team.",
        ]
        if lead.services_text.strip():
            paragraphs.append(
                "The areas noted in our research include: " + lead.services_text.strip()[:1200] + "."
            )
        if lead.evidence_text.strip():
            paragraphs.append(
                "Research context recorded for this company: " + lead.evidence_text.strip()[:900]
            )
        if payload.context.strip():
            paragraphs.append(payload.context.strip())
        paragraphs.extend([
            "Would you be open to a brief conversation to see whether there may be a fit?",
            "Best regards,\n[Your name]",
        ])
    if payload.channel == "linkedin":
        subject = ""
    return subject, "\n\n".join(paragraphs)


@app.post("/leads/{lead_id}/outreach-drafts", response_model=OutreachDraftRead, status_code=201)
def create_outreach_draft(
    lead_id: int,
    payload: OutreachDraftCreate,
    db: Session = Depends(get_db),
):
    """Save a draft only. This endpoint never sends messages."""
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    subject, body = _build_outreach_copy(lead, payload)
    draft = OutreachDraft(
        lead_id=lead_id,
        channel=payload.channel,
        subject=subject,
        body=body,
        status="draft",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


@app.get("/leads/{lead_id}/outreach-drafts", response_model=list[OutreachDraftRead])
def list_outreach_drafts(lead_id: int, db: Session = Depends(get_db)):
    if db.get(Lead, lead_id) is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    statement = (
        select(OutreachDraft)
        .where(OutreachDraft.lead_id == lead_id)
        .order_by(OutreachDraft.created_at.desc())
    )
    return list(db.scalars(statement).all())


@app.get("/analytics/pipeline", response_model=PipelineSummary)
def get_pipeline_summary(db: Session = Depends(get_db)):
    statuses = ["new", "contacted", "replied", "call", "proposal", "won", "lost"]
    grouped = db.execute(
        select(Lead.status, func.count(Lead.id)).group_by(Lead.status)
    ).all()
    by_status = {status: 0 for status in statuses}
    by_status.update({status: count for status, count in grouped})
    return PipelineSummary(
        total_leads=sum(by_status.values()),
        by_status=by_status,
        total_interactions=db.scalar(select(func.count(LeadInteraction.id))) or 0,
        total_drafts=db.scalar(select(func.count(OutreachDraft.id))) or 0,
    )
