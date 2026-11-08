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

    def search_companies(self, query: str, location: str | None = None,
                         country: str | None = None, limit: int = 10) -> list[dict]:
        if not self.api_key:
            raise SourceFetchError("EXA_API_KEY is not configured. Add it to the API server environment.")
        search_query = query.strip()
        if location:
            search_query += f" companies located in {location}"
        body = {"query": search_query, "type": "lite", "category": "company",
                "numResults": min(max(limit, 1), 20), "contents": {"highlights": True}}
        if country:
            body["userLocation"] = country.upper()
        try:
            response = httpx.post(self.base_url,
                headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                json=body, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceFetchError("Exa search request failed or returned invalid JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("results", []), list):
            raise SourceContractError("Unexpected Exa response: expected a results list")
        results = []
        for item in data.get("results", []):
            if not isinstance(item, dict) or not item.get("url") or not item.get("title"):
                continue
            highlights = item.get("highlights") or []
            results.append({"company_name": str(item["title"]).strip()[:200],
                "source_url": str(item["url"]).strip(),
                "snippet": " ".join(str(x) for x in highlights if x)[:3000],
                "location": location or "unspecified", "source": self.source_name,
                "search_query": query})
        return results
