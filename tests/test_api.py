from fastapi.testclient import TestClient
from app.main import app

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
        "public_contact": "hello@example-automation.invalid"
    }
    created = client.post("/leads", json=payload)
    assert created.status_code == 201
    lead_id = created.json()["id"]
    assert created.json()["score"] > 0

    fetched = client.get(f"/leads/{lead_id}")
    assert fetched.status_code == 200
    assert fetched.json()["company_name"] == payload["company_name"]

def test_duplicate_website_rejected():
    payload = {
        "company_name": "Duplicate Test Agency",
        "website": "https://duplicate-test.invalid",
        "services_text": "automation"
    }
    first = client.post("/leads", json=payload)
    second = client.post("/leads", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409
