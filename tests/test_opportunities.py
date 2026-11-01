import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.source_schemas import JobOpportunity


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


def make_job(
    *,
    external_id="listing-123",
    title="Python Backend Developer",
    remote=True,
):
    return JobOpportunity(
        source="arbeitnow",
        external_id=external_id,
        company_name="Example GmbH",
        title=title,
        location="Berlin, Germany",
        remote=remote,
        tags=["Python", "FastAPI"],
        job_types=["full_time"],
        description="Build Python APIs and automation systems.",
        source_url="https://www.arbeitnow.com/view/listing-123",
        created_at=1750800000,
    )


def test_sync_creates_new_opportunity(monkeypatch, client_with_database):
    monkeypatch.setattr(
        "app.main.ArbeitnowAdapter.fetch_jobs",
        lambda self, page=1: [make_job()],
    )

    response = client_with_database.post("/sources/arbeitnow/sync?page=1")

    assert response.status_code == 200, response.json()
    assert response.json() == {
        "source": "arbeitnow",
        "fetched": 1,
        "created": 1,
        "updated": 0,
        "unchanged": 0,
    }
    listed = client_with_database.get("/opportunities")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["external_id"] == "listing-123"


def test_sync_is_idempotent_for_unchanged_records(monkeypatch, client_with_database):
    monkeypatch.setattr(
        "app.main.ArbeitnowAdapter.fetch_jobs",
        lambda self, page=1: [make_job()],
    )

    first = client_with_database.post("/sources/arbeitnow/sync")
    second = client_with_database.post("/sources/arbeitnow/sync")

    assert first.json()["created"] == 1
    assert second.json()["created"] == 0
    assert second.json()["unchanged"] == 1
    assert len(client_with_database.get("/opportunities").json()) == 1


def test_sync_updates_existing_record(monkeypatch, client_with_database):
    jobs = [make_job(), make_job(title="Senior Python Developer")]

    def fake_fetch(self, page=1):
        return [jobs.pop(0)]

    monkeypatch.setattr("app.main.ArbeitnowAdapter.fetch_jobs", fake_fetch)

    first = client_with_database.post("/sources/arbeitnow/sync")
    second = client_with_database.post("/sources/arbeitnow/sync")

    assert first.json()["created"] == 1
    assert second.json()["updated"] == 1
    item = client_with_database.get("/opportunities").json()[0]
    assert item["title"] == "Senior Python Developer"


def test_opportunity_filters_by_remote_location_and_keyword(
    monkeypatch, client_with_database
):
    monkeypatch.setattr(
        "app.main.ArbeitnowAdapter.fetch_jobs",
        lambda self, page=1: [
            make_job(external_id="remote-1", remote=True),
            make_job(
                external_id="onsite-1",
                title="Frontend Engineer",
                remote=False,
            ),
        ],
    )
    client_with_database.post("/sources/arbeitnow/sync")

    response = client_with_database.get(
        "/opportunities?remote=true&location=Berlin&keyword=Python"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["external_id"] == "remote-1"


def test_get_opportunity_returns_404_for_unknown_id(client_with_database):
    response = client_with_database.get("/opportunities/999")
    assert response.status_code == 404
