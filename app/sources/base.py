from typing import Protocol

from app.source_schemas import JobOpportunity


class SourceFetchError(Exception):
    """Raised when an external source cannot be reached."""


class SourceContractError(Exception):
    """Raised when an external source returns an unexpected payload."""


class JobSourceAdapter(Protocol):
    source_name: str

    def fetch_jobs(self, page: int = 1) -> list[JobOpportunity]:
        ...
