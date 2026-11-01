import httpx
import pytest

from app.source_schemas import JobOpportunity
from app.sources.arbeitnow import ArbeitnowAdapter
from app.sources.base import SourceContractError, SourceFetchError


def test_arbeitnow_adapter_normalizes_job(monkeypatch):
    payload = {
        "data": [
            {
                "slug": "python-developer-example",
                "company_name": "Example GmbH",
                "title": "Python Developer",
                "location": "Berlin, Germany",
                "remote": True,
                "tags": ["Python", "FastAPI"],
                "job_types": ["full_time"],
                "description": "<p>Build APIs.</p>",
                "url": "https://www.arbeitnow.com/view/python-developer-example",
                "created_at": 1750800000,
            }
        ]
    }

    def fake_get(url, **kwargs):
        assert url == ArbeitnowAdapter.base_url
        assert kwargs["params"] == {"page": 2}
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    jobs = ArbeitnowAdapter().fetch_jobs(page=2)

    assert len(jobs) == 1
    job = jobs[0]
    assert isinstance(job, JobOpportunity)
    assert job.source == "arbeitnow"
    assert job.external_id == "python-developer-example"
    assert job.company_name == "Example GmbH"
    assert job.remote is True
    assert job.tags == ["Python", "FastAPI"]


def test_arbeitnow_adapter_rejects_unexpected_payload(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(200, json={"items": []}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(SourceContractError):
        ArbeitnowAdapter().fetch_jobs()


def test_arbeitnow_adapter_reports_http_failure(monkeypatch):
    def fake_get(url, **kwargs):
        return httpx.Response(503, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(SourceFetchError):
        ArbeitnowAdapter().fetch_jobs()
