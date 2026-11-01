import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def outreach_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_lead(client):
    response = client.post("/leads", json={
        "company_name": "Northstar Automation",
        "website": "https://northstar.example",
        "services_text": "Python, FastAPI, workflow automation",
        "evidence_text": "Public job listing mentions API integrations",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_interaction_updates_pipeline_status_and_is_listed(outreach_client):
    lead = create_lead(outreach_client)
    created = outreach_client.post(f"/leads/{lead['id']}/interactions", json={
        "interaction_type": "contacted",
        "notes": "Sent a manually prepared introduction",
        "next_action_at": "2026-11-05T10:00:00Z",
    })
    assert created.status_code == 201, created.text
    assert created.json()["interaction_type"] == "contacted"
    assert outreach_client.get(f"/leads/{lead['id']}").json()["status"] == "contacted"

    second = outreach_client.post(f"/leads/{lead['id']}/interactions", json={
        "interaction_type": "replied",
        "notes": "They asked for more information",
    })
    assert second.status_code == 201
    assert outreach_client.get(f"/leads/{lead['id']}").json()["status"] == "replied"
    history = outreach_client.get(f"/leads/{lead['id']}/interactions")
    assert history.status_code == 200
    assert len(history.json()) == 2


def test_invalid_interaction_type_is_rejected(outreach_client):
    lead = create_lead(outreach_client)
    response = outreach_client.post(f"/leads/{lead['id']}/interactions", json={
        "interaction_type": "sent_email",
    })
    assert response.status_code == 422


def test_interaction_for_missing_lead_returns_404(outreach_client):
    response = outreach_client.post("/leads/999/interactions", json={
        "interaction_type": "contacted",
    })
    assert response.status_code == 404


def test_outreach_draft_is_saved_but_never_sent(outreach_client):
    lead = create_lead(outreach_client)
    response = outreach_client.post(f"/leads/{lead['id']}/outreach-drafts", json={
        "channel": "email",
        "tone": "professional",
        "context": "I can help assess a small API integration project.",
    })
    assert response.status_code == 201, response.text
    draft = response.json()
    assert draft["status"] == "draft"
    assert draft["subject"]
    assert "Northstar Automation" in draft["body"]
    assert "Python, FastAPI" in draft["body"]
    assert "I can help assess a small API integration project." in draft["body"]
    assert len(outreach_client.get(f"/leads/{lead['id']}/outreach-drafts").json()) == 1


def test_linkedin_draft_has_no_subject_and_pipeline_analytics(outreach_client):
    lead = create_lead(outreach_client)
    draft = outreach_client.post(f"/leads/{lead['id']}/outreach-drafts", json={
        "channel": "linkedin",
        "tone": "concise",
    })
    assert draft.status_code == 201
    assert draft.json()["subject"] == ""
    summary = outreach_client.get("/analytics/pipeline")
    assert summary.status_code == 200
    assert summary.json()["total_leads"] == 1
    assert summary.json()["by_status"]["new"] == 1
    assert summary.json()["total_drafts"] == 1
