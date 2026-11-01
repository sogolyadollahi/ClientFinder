from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class JobOpportunity(BaseModel):
    """A normalized job listing; it is not yet a qualified company Lead."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source: str = Field(min_length=1, max_length=50)
    external_id: str = Field(min_length=1, max_length=300)
    company_name: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    location: str = Field(default="unknown", max_length=200)
    remote: bool = False
    tags: list[str] = Field(default_factory=list)
    job_types: list[str] = Field(default_factory=list)
    description: str = ""
    source_url: HttpUrl
    created_at: int | None = None


class JobOpportunityPage(BaseModel):
    source: str
    page: int
    count: int
    results: list[JobOpportunity]


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    external_id: str
    company_name: str
    title: str
    location: str
    remote: bool
    tags: list[str]
    job_types: list[str]
    description: str
    source_url: str
    source_created_at: int | None
    first_seen_at: datetime
    last_seen_at: datetime


class OpportunitySyncResult(BaseModel):
    source: str
    fetched: int
    created: int
    updated: int
    unchanged: int
