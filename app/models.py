from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
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
