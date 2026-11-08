import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.source_schemas import JobOpportunity
from app.sources.base import SourceFetchError
from app.sources.serpapi import SerpApiAdapter
from app.sources.exa import ExaAdapter


@pytest.fixture
def client_with_database():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def test_exa_requires_server_side_key(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    with pytest.raises(SourceFetchError, match="EXA_API_KEY"):
        ExaAdapter().search_companies("software agencies")


def test_exa_company_search_returns_results_without_persisting(monkeypatch, client_with_database):
    results = [{
        "company_name": "Example Agency",
        "source_url": "https://example-agency.com/about",
        "snippet": "Software development agency focused on Python automation and API integration.",
        "location": "Berlin, Germany", "source": "exa_company_search",
        "search_query": "Python automation agencies",
    }]
    monkeypatch.setattr("app.main.ExaAdapter.search_companies", lambda self, **kwargs: results)
    response = client_with_database.post("/discovery/companies/search", json={
        "query": "Python automation agencies", "location": "Berlin, Germany",
        "country": "DE", "limit": 10,
    })
    assert response.status_code == 200, response.text
    assert response.json()["fetched"] == 1
    assert response.json()["results"][0]["qualification_score"] >= 50
    assert client_with_database.get("/company-prospects").json() == []


def test_dynamic_job_search_upserts_opportunities(monkeypatch, client_with_database):
    job = JobOpportunity(
        source="serpapi_google_jobs",
        external_id="google-job-123",
        company_name="Example Tech",
        title="Python Backend Contractor",
        location="Remote, Germany",
        remote=True,
        tags=["Python", "FastAPI"],
        job_types=["Contract"],
        description="Build APIs and automation.",
        source_url="https://example.com/jobs/123",
        created_at=None,
    )
    monkeypatch.setattr(
        "app.main.SerpApiAdapter.search_jobs",
        lambda self, **kwargs: [job],
    )
    payload = {"query": "Python backend contractor", "location": "Germany", "country": "DE"}
    first = client_with_database.post("/discovery/jobs/search", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 1
    second = client_with_database.post("/discovery/jobs/search", json=payload)
    assert second.status_code == 200
    assert second.json()["created"] == 0
    assert second.json()["unchanged"] == 1
    stored = client_with_database.get("/opportunities?source=serpapi_google_jobs")
    assert stored.status_code == 200
    assert len(stored.json()) == 1
