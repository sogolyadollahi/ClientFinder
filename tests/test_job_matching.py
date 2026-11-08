import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.job_matching import score_job
from app.main import app


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


def test_junior_python_backend_role_scores_as_strong_match():
    fit = score_job(
        title="Junior Python Backend Developer",
        description="Build REST APIs with FastAPI, PostgreSQL, SQLAlchemy, Docker and Pytest.",
        tags=["Python", "FastAPI", "PostgreSQL"],
        job_types=["full_time"],
        remote=True,
    )
    assert fit.score >= 75
    assert fit.category == "strong_match"
    assert "python" in fit.matched_skills
    assert "fastapi" in fit.matched_skills


def test_senior_role_is_excluded():
    fit = score_job(
        title="Senior Python Backend Engineer",
        description="Python, FastAPI, PostgreSQL",
        remote=True,
    )
    assert fit.score == 0
    assert fit.category == "not_a_fit"


def test_n8n_ingestion_keeps_remote_jobs_and_creates_match(client_with_database):
    response = client_with_database.post("/integrations/n8n/jobs", json={
        "remote_only": True,
        "jobs": [
            {
                "source": "arbeitnow", "external_id": "junior-python-1",
                "company_name": "Example Tech", "title": "Junior Python Backend Developer",
                "location": "Remote - Europe", "remote": True,
                "tags": ["Python", "FastAPI", "PostgreSQL"],
                "job_types": ["full_time"],
                "description": "Build REST APIs with SQLAlchemy, Docker and Pytest.",
                "source_url": "https://example.com/jobs/junior-python-1",
                "created_at": 1762500000
            },
            {
                "source": "arbeitnow", "external_id": "onsite-python-2",
                "company_name": "Office Tech", "title": "Python Developer",
                "location": "Berlin", "remote": False,
                "tags": ["Python"], "job_types": ["full_time"],
                "description": "Build internal tools.",
                "source_url": "https://example.com/jobs/onsite-python-2",
                "created_at": 1762500000
            }
        ]
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["received"] == 2
    assert payload["skipped_non_remote"] == 1
    assert payload["created"] == 1
    assert payload["matches_created"] == 1

    matches = client_with_database.get("/job-matches?min_score=70")
    assert matches.status_code == 200
    assert len(matches.json()) == 1
    assert matches.json()[0]["title"] == "Junior Python Backend Developer"
    assert matches.json()[0]["match_category"] == "strong_match"


def test_n8n_ingestion_is_idempotent(client_with_database):
    payload = {
        "remote_only": True,
        "jobs": [{
            "source": "arbeitnow", "external_id": "same-job",
            "company_name": "Example", "title": "Python Automation Developer",
            "location": "Remote", "remote": True, "tags": ["Python", "Automation"],
            "job_types": ["contract"], "description": "API integration",
            "source_url": "https://example.com/jobs/same-job"
        }]
    }
    first = client_with_database.post("/integrations/n8n/jobs", json=payload)
    second = client_with_database.post("/integrations/n8n/jobs", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["created"] == 1
    assert second.json()["created"] == 0
    assert second.json()["unchanged"] == 1
    assert second.json()["matches_updated"] == 1
