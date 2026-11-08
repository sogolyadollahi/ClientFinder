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


def test_serpapi_requires_server_side_key(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    with pytest.raises(SourceFetchError, match="SERPAPI_API_KEY"):
        SerpApiAdapter().search_companies("software agencies")


def test_live_company_search_persists_and_deduplicates(monkeypatch, client_with_database):
    results = [{
        "external_id": "https://example-agency.com/about",
        "company_name": "Example Agency - Software Development",
        "source_url": "https://example-agency.com/about",
        "snippet": "We are a software development agency focused on Python automation and API integration.",
        "location": "Berlin, Germany",
        "source": "serpapi_google",
        "search_query": "Python automation agencies",
    }]
    monkeypatch.setattr(
        "app.main.SerpApiAdapter.search_companies",
        lambda self, **kwargs: results,
    )
    payload = {
        "query": "Python automation agencies",
        "location": "Berlin, Germany",
        "country": "DE",
        "limit": 10,
    }
    first = client_with_database.post("/discovery/companies/search", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 1
    assert first.json()["results"][0]["qualification_score"] >= 50

    second = client_with_database.post("/discovery/companies/search", json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["created"] == 0
    assert second.json()["updated"] == 1
    assert len(client_with_database.get("/company-prospects").json()) == 1


def test_company_prospect_can_enter_review_and_be_promoted(monkeypatch, client_with_database):
    monkeypatch.setattr(
        "app.main.SerpApiAdapter.search_companies",
        lambda self, **kwargs: [{
            "external_id": "https://agency.example/",
            "company_name": "Automation Agency",
            "source_url": "https://agency.example/",
            "snippet": "Automation consultancy providing API integration and Python services.",
            "location": "Amsterdam, Netherlands",
            "source": "serpapi_google",
            "search_query": "automation agency",
        }],
    )
    search = client_with_database.post("/discovery/companies/search", json={
        "query": "automation agency", "location": "Amsterdam", "country": "NL",
    })
    assert search.status_code == 200
    prospect_id = search.json()["results"][0]["id"]

    review = client_with_database.post(f"/company-prospects/{prospect_id}/review")
    assert review.status_code == 201, review.text
    review_id = review.json()["id"]

    verified = client_with_database.patch(f"/companies/reviews/{review_id}", json={
        "official_website": "https://agency.example",
        "verification_status": "verified",
        "verification_notes": "Official website checked manually",
    })
    assert verified.status_code == 200
    promoted = client_with_database.post(f"/companies/reviews/{review_id}/promote")
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["lead"]["website"] == "https://agency.example"


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
