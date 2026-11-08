from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CompanySearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    limit: int = Field(default=10, ge=1, le=20)


class CompanyDiscoveryResult(BaseModel):
    id: int
    company_name: str
    source_url: HttpUrl
    snippet: str
    location: str
    source: str
    search_query: str
    qualification_score: int = Field(ge=0, le=100)
    score_reasons: list[str]


class CompanySearchResponse(BaseModel):
    query: str
    source: str
    fetched: int
    created: int
    updated: int
    results: list[CompanyDiscoveryResult]


class JobSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    location: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    limit: int = Field(default=10, ge=1, le=20)


class DynamicJobSearchResponse(BaseModel):
    query: str
    source: str
    fetched: int
    created: int
    updated: int
    unchanged: int
    results: list[dict]


class CompanyProspectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    company_name: str
    normalized_key: str
    source_url: HttpUrl
    snippet: str
    location: str
    search_query: str
    qualification_score: int
    score_reasons: list[str]


class LiveCompanyDiscoveryResult(BaseModel):
    company_name: str
    source_url: HttpUrl
    snippet: str = ""
    location: str
    source: str
    search_query: str
    qualification_score: int = Field(ge=0, le=100)
    score_reasons: list[str]


class LiveCompanySearchResponse(BaseModel):
    query: str
    source: str
    fetched: int
    results: list[LiveCompanyDiscoveryResult]
