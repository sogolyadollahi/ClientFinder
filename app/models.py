from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("website", name="uq_lead_website"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    website: Mapped[str] = mapped_column(String(500), nullable=False)
    region: Mapped[str] = mapped_column(String(100), default="unknown")
    company_size: Mapped[str] = mapped_column(String(30), default="unknown")
    opportunity_types: Mapped[str] = mapped_column(String(100), default="both")
    services_text: Mapped[str] = mapped_column(Text, default="")
    evidence_text: Mapped[str] = mapped_column(Text, default="")
    public_contact: Mapped[str | None] = mapped_column(String(320), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    score_reasons: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_opportunity_source_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(300), nullable=False)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(200), default="unknown", index=True)
    remote: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    job_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_created_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
