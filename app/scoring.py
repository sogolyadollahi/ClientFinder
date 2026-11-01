from dataclasses import dataclass

@dataclass(frozen=True)
class ScoreResult:
    score: int
    reasons: list[str]

AGENCY_KEYWORDS = {
    "automation": 12,
    "workflow automation": 12,
    "n8n": 10,
    "make.com": 8,
    "zapier": 8,
    "crm": 10,
    "hubspot": 8,
    "salesforce": 8,
    "api integration": 12,
    "ai integration": 8,
    "python": 6,
    "software development": 5,
}
HIRING_KEYWORDS = {
    "we are hiring": 15,
    "careers": 8,
    "join our team": 12,
    "freelance": 12,
    "contractor": 12,
    "remote": 8,
    "internship": 10,
    "backend developer": 10,
    "python developer": 10,
}

def calculate_score(
    services_text: str,
    evidence_text: str,
    company_size: str = "unknown",
    has_public_contact: bool = False,
) -> ScoreResult:
    services = (services_text or "").lower()
    evidence = (evidence_text or "").lower()
    reasons: list[str] = []

    relevance = min(30, sum(points for word, points in AGENCY_KEYWORDS.items() if word in services))
    if relevance:
        reasons.append(f"Service relevance: {relevance}/30")

    hiring = min(25, sum(points for word, points in HIRING_KEYWORDS.items() if word in evidence))
    if hiring:
        reasons.append(f"Hiring/collaboration signals: {hiring}/25")

    size_points = {"small": 15, "medium": 12, "large": 8, "unknown": 0}.get(company_size, 0)
    if size_points:
        reasons.append(f"Company size fit: {size_points}/15")

    remote_points = 20 if "remote" in evidence else 0
    if remote_points:
        reasons.append(f"Remote-work signal: {remote_points}/20")

    contact_points = 10 if has_public_contact else 0
    if contact_points:
        reasons.append(f"Public business contact: {contact_points}/10")

    score = min(100, relevance + hiring + size_points + remote_points + contact_points)
    return ScoreResult(score=score, reasons=reasons)
