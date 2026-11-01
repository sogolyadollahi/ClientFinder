import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def isolated_database():
    """Give each test a fresh in-memory database."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_fetch_lead():
    payload = {
        "company_name": "Example Automation Agency",
        "website": "https://example-automation.invalid",
        "region": "Europe",
        "company_size": "small",
        "opportunity_types": "both",
        "services_text": "n8n automation, CRM, API integration and Python",
        "evidence_text": "We are hiring remote freelance developers",
        "public_contact": "hello@example.com",
    }
    created = client.post("/leads", json=payload)
    assert created.status_code == 201, created.json()
    lead_id = created.json()["id"]
    assert created.json()["score"] > 0

    fetched = client.get(f"/leads/{lead_id}")
    assert fetched.status_code == 200
    assert fetched.json()["company_name"] == payload["company_name"]


def test_duplicate_website_rejected():
    payload = {
        "company_name": "Duplicate Test Agency",
        "website": "https://duplicate-test.invalid",
        "services_text": "automation",
    }
    first = client.post("/leads", json=payload)
    second = client.post("/leads", json=payload)
    assert first.status_code == 201, first.json()
    assert second.status_code == 409
