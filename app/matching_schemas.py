from pydantic import BaseModel, Field

from .source_schemas import JobOpportunity


class N8nJobBatch(BaseModel):
    jobs: list[JobOpportunity] = Field(max_length=100)
    remote_only: bool = True


class JobMatchRead(BaseModel):
    opportunity_id: int
    source: str
    company_name: str
    title: str
    location: str
    remote: bool
    tags: list[str]
    job_types: list[str]
    source_url: str
    match_score: int
    match_category: str
    match_reasons: list[str]
    matched_skills: list[str]
    missing_skills: list[str]


class N8nJobIngestResponse(BaseModel):
    source: str
    received: int
    skipped_non_remote: int
    created: int
    updated: int
    unchanged: int
    matches_created: int
    matches_updated: int
