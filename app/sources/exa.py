"""Exa Search API adapter for ephemeral company discovery."""
import os

import httpx

from app.sources.base import SourceContractError, SourceFetchError


class ExaAdapter:
    base_url = "https://api.exa.ai/search"
    source_name = "exa_company_search"

    def __init__(self, api_key: str | None = None, timeout: float = 20.0):
        self.api_key = api_key or os.getenv("EXA_API_KEY")
        self.timeout = timeout

    def search_companies(
        self,
        query: str,
        location: str | None = None,
        country: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        if not self.api_key:
            raise SourceFetchError(
                "EXA_API_KEY is not configured. Add it to the API server environment."
            )

        search_query = query.strip()
        if location:
            search_query += f" companies located in {location}"

        body = {
            "query": search_query,
            "type": "lite",
            "category": "company",
            "numResults": min(max(limit, 1), 20),
            "contents": {"highlights": True},
        }
        if country:
            body["userLocation"] = country.upper()

        try:
            response = httpx.post(
                self.base_url,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "ClientFinder/1.0 (Exa API integration)",
                },
                json=body,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise SourceFetchError("Exa request timed out. Retry the search.") from exc
        except httpx.RequestError as exc:
            raise SourceFetchError(
                f"Could not connect to Exa ({type(exc).__name__}). Check network access."
            ) from exc

        if response.is_error:
            # Keep the diagnostic useful without exposing request headers or API keys.
            detail = " ".join(response.text.split())[:500]
            cf_ray = response.headers.get("cf-ray")
            diagnostic = f" Cloudflare Ray ID: {cf_ray}." if cf_ray else ""
            raise SourceFetchError(
                f"Exa returned HTTP {response.status_code}:{diagnostic} "
                f"{detail or 'empty response body'}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            detail = " ".join(response.text.split())[:300]
            raise SourceFetchError(
                f"Exa returned HTTP {response.status_code} but response was not valid JSON: "
                f"{detail or 'empty response body'}"
            ) from exc

        if not isinstance(data, dict) or not isinstance(data.get("results", []), list):
            raise SourceContractError("Unexpected Exa response: expected a results list")

        results = []
        for item in data.get("results", []):
            if not isinstance(item, dict) or not item.get("url") or not item.get("title"):
                continue
            highlights = item.get("highlights") or []
            results.append(
                {
                    "company_name": str(item["title"]).strip()[:200],
                    "source_url": str(item["url"]).strip(),
                    "snippet": " ".join(str(x) for x in highlights if x)[:3000],
                    "location": location or "unspecified",
                    "source": self.source_name,
                    "search_query": query,
                }
            )
        return results
