import httpx
from pydantic import ValidationError

from app.source_schemas import JobOpportunity
from app.sources.base import SourceContractError, SourceFetchError


class ArbeitnowAdapter:
    """Read and normalize public job listings from the Arbeitnow job-board API."""

    source_name = "arbeitnow"
    base_url = "https://www.arbeitnow.com/api/job-board-api"

    def fetch_jobs(self, page: int = 1) -> list[JobOpportunity]:
        try:
            response = httpx.get(
                self.base_url,
                params={"page": page},
                timeout=15.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SourceFetchError("Could not fetch valid JSON from Arbeitnow") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise SourceContractError(
                "Unexpected Arbeitnow response: expected an object with a data array"
            )

        normalized: list[JobOpportunity] = []
        for index, item in enumerate(payload["data"]):
            if not isinstance(item, dict):
                raise SourceContractError(f"Invalid job record at data[{index}]")

            try:
                normalized.append(
                    JobOpportunity(
                        source=self.source_name,
                        external_id=str(item.get("slug") or item.get("url") or ""),
                        company_name=item.get("company_name") or "",
                        title=item.get("title") or "",
                        location=item.get("location") or "unknown",
                        remote=bool(item.get("remote", False)),
                        tags=item.get("tags") or [],
                        job_types=item.get("job_types") or [],
                        description=item.get("description") or "",
                        source_url=item.get("url") or "",
                        created_at=item.get("created_at"),
                    )
                )
            except (ValidationError, TypeError, ValueError) as exc:
                raise SourceContractError(
                    f"Invalid Arbeitnow job record at data[{index}]"
                ) from exc

        return normalized
