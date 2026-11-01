from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


class LeadCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    website: HttpUrl
    region: str = Field(default="unknown", max_length=100)
    company_size: str = Field(default="unknown", pattern="^(small|medium|large|unknown)$")
    opportunity_types: str = Field(default="both", pattern="^(projects|internships|both)$")
    services_text: str = Field(default="", max_length=5000)
    evidence_text: str = Field(default="", max_length=5000)
    public_contact: EmailStr | None = None


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    website: str
    region: str
    company_size: str
    opportunity_types: str
    services_text: str
    evidence_text: str
    public_contact: str | None
    score: int
    score_reasons: str
    status: str


class CompanyReviewCreate(BaseModel):
    normalized_key: str = Field(min_length=1, max_length=250)
    company_name: str = Field(min_length=2, max_length=200)


class CompanyReviewUpdate(BaseModel):
    official_website: HttpUrl | None = None
    verification_status: Literal["pending", "verified", "rejected"]
    verification_notes: str = Field(default="", max_length=5000)


class CompanyReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    normalized_key: str
    company_name: str
    official_website: str | None
    verification_status: str
    verification_notes: str
    lead_id: int | None
    created_at: datetime
    updated_at: datetime


class LeadPromotionResult(BaseModel):
    review: CompanyReviewRead
    lead: LeadRead


