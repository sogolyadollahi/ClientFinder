"""SerpApi integration for live web-company and Google Jobs discovery.

The API key is read only from the server environment. Never expose it to Streamlit.
"""
import os

import httpx

from app.source_schemas import JobOpportunity
from app.sources.base import SourceContractError, SourceFetchError


class SerpApiAdapter:
    """Search adapter for SerpApi's Google Search and Google Jobs engines."""

    base_url = "https://serpapi.com/search.json"
    source_name = "serpapi_google_jobs"

    def __init__(self, api_key: str | None = None, timeout: float = 20.0):
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY")
        self.timeout = timeout

    def _request(self, params: dict) -> dict:
        if not self.api_key:
            raise SourceFetchError(
                "SERPAPI_API_KEY is not configured. Add it to the API environment."
            )
        request_params = {**params, "api_key": self.api_key}
        try:
            response = httpx.get(
                self.base_url,
                params=request_params,
                timeout=self.timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceFetchError("SerpApi request failed or returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise SourceContractError("Unexpected SerpApi response: expected a JSON object")
        if payload.get("error"):
            raise SourceFetchError(str(payload["error"]))
        return payload

    def search_companies(
        self,
        query: str,
        location: str | None = None,
        limit: int = 10,
        country: str | None = None,
    ) -> list[dict]:
        params = {"engine": "google", "q": query, "num": min(max(limit, 1), 20)}
        if location:
            params["location"] = location
        if country:
            params["gl"] = country.lower()
        payload = self._request(params)
        organic = payload.get("organic_results", [])
        if not isinstance(organic, list):
            raise SourceContractError("Unexpected Google Search response: organic_results is not a list")

        results = []
        for item in organic:
            if not isinstance(item, dict) or not item.get("link") or not item.get("title"):
                continue
            results.append({
                "external_id": str(item["link"]).strip(),
                "company_name": str(item["title"]).strip()[:200],
                "source_url": str(item["link"]).strip(),
                "snippet": str(item.get("snippet") or "").strip()[:3000],
                "location": location or "unknown",
                "source": "serpapi_google",
                "search_query": query,
            })
        return results

    def search_jobs(
        self,
        query: str,
        location: str | None = None,
        limit: int = 10,
        country: str | None = None,
    ) -> list[JobOpportunity]:
        params = {"engine": "google_jobs", "q": query}
        if location:
            params["location"] = location
        if country:
            params["gl"] = country.lower()
        payload = self._request(params)
        jobs = payload.get("jobs_results", [])
        if not isinstance(jobs, list):
            raise SourceContractError("Unexpected Google Jobs response: jobs_results is not a list")

        normalized = []
        for index, item in enumerate(jobs[:min(max(limit, 1), 20)]):
            if not isinstance(item, dict):
                raise SourceContractError(f"Invalid Google Jobs record at jobs_results[{index}]")
            job_id = item.get("job_id") or item.get("share_link")
            apply_options = item.get("apply_options") or []
            source_url = (
                (apply_options[0].get("link") if apply_options and isinstance(apply_options[0], dict) else None)
                or item.get("share_link")
            )
            if not job_id or not source_url or not item.get("title") or not item.get("company_name"):
                continue
            detected = item.get("detected_extensions") or {}
            extensions = item.get("extensions") or []
            normalized.append(JobOpportunity(
                source=self.source_name,
                external_id=str(job_id),
                company_name=str(item["company_name"])[:200],
                title=str(item["title"])[:300],
                location=str(item.get("location") or location or "unknown")[:200],
                remote=bool(detected.get("work_from_home", False)),
                tags=[str(value) for value in extensions[:30]],
                job_types=[str(detected.get("schedule_type"))] if detected.get("schedule_type") else [],
                description=str(item.get("description") or "")[:12000],
                source_url=str(source_url),
                created_at=None,
            ))
        return normalized
