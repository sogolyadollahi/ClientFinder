import re
import unicodedata
from collections import defaultdict
from typing import Iterable

from .models import Opportunity


SKILL_PATTERNS = {
    "Python": r"\bpython\b",
    "FastAPI": r"\bfastapi\b",
    "Django": r"\bdjango\b",
    "Flask": r"\bflask\b",
    "JavaScript": r"\bjavascript\b",
    "TypeScript": r"\btypescript\b",
    "React": r"\breact(?:\.js)?\b",
    "Node.js": r"\bnode(?:\.js)?\b",
    "Java": r"\bjava\b",
    "C#": r"\bc#\b",
    ".NET": r"\b\.net\b",
    "PHP": r"\bphp\b",
    "Go": r"\bgolang\b|\bgo\s+(?:language|programming)\b",
    "Ruby": r"\bruby\b",
    "SQL": r"\bsql\b",
    "PostgreSQL": r"\bpostgres(?:ql)?\b",
    "AWS": r"\baws\b|amazon web services",
    "Docker": r"\bdocker\b",
    "Kubernetes": r"\bkubernetes\b|\bk8s\b",
    "Machine Learning": r"\bmachine learning\b|\bml\b",
}

LEGAL_SUFFIXES = {
    "gmbh", "ug", "ag", "ltd", "limited", "llc", "inc", "incorporated",
    "corp", "corporation", " srl", "srl", "bv", " oy", "sas", "plc",
}


def normalize_company_key(name: str) -> str:
    """Create a conservative grouping key; this is not legal-entity resolution."""
    value = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    tokens = value.split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _contains(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def build_company_candidates(opportunities: Iterable[Opportunity]) -> list[dict]:
    grouped: dict[str, list[Opportunity]] = defaultdict(list)
    for opportunity in opportunities:
        key = normalize_company_key(opportunity.company_name)
        if key:
            grouped[key].append(opportunity)

    candidates = []
    for key, records in grouped.items():
        combined_text = " ".join(
            [
                " ".join(record.tags or [])
                + " "
                + record.title
                + " "
                + (record.description or "")
                for record in records
            ]
        )
        skills = [
            skill for skill, pattern in SKILL_PATTERNS.items()
            if _contains(combined_text, pattern)
        ]
        titles = [record.title for record in records]
        remote_count = sum(bool(record.remote) for record in records)
        engineering_count = sum(
            1 for title in titles
            if _contains(title, r"engineer|developer|software|backend|frontend|full.?stack|devops|data")
        )
        contractor_signal = _contains(
            combined_text,
            r"\b(freelance|freelancer|contractor|independent contractor|external partner|agency|consultancy|consulting partner|staff augmentation|outsourcing)\b",
        )

        score = 0
        reasons = []
        evidence = []
        if skills:
            points = min(30, len(skills) * 5)
            score += points
            reasons.append(f"{points} points: technical skills detected")
            evidence.append("Detected skills: " + ", ".join(skills))
        if len(records) >= 2:
            score += 15
            reasons.append("15 points: multiple active job listings")
            evidence.append(f"{len(records)} listings observed for this company")
        if engineering_count:
            score += 15
            reasons.append("15 points: engineering or technical roles detected")
            evidence.append(f"{engineering_count} technical role(s): " + "; ".join(titles[:5]))
        if remote_count:
            score += 10
            reasons.append("10 points: at least one remote role")
            evidence.append(f"{remote_count} of {len(records)} listing(s) marked remote")
        if contractor_signal:
            score += 20
            reasons.append("20 points: explicit external-work or contract language")
            evidence.append("Contract/freelance/agency language found in listing text")
        if len(records) >= 3:
            score += 10
            reasons.append("10 points: sustained hiring volume (3+ listings)")

        locations = sorted({record.location for record in records if record.location})
        candidates.append(
            {
                "company_name": records[0].company_name,
                "normalized_key": key,
                "opportunity_count": len(records),
                "opportunity_ids": [record.id for record in records],
                "job_titles": titles[:10],
                "locations": locations[:10],
                "remote_opportunity_count": remote_count,
                "detected_skills": skills,
                "signals": {
                    "technical_roles": engineering_count > 0,
                    "multiple_openings": len(records) >= 2,
                    "remote_hiring": remote_count > 0,
                    "external_work_language": contractor_signal,
                },
                "qualification_score": min(score, 100),
                "score_reasons": reasons,
                "evidence": evidence,
                "review_status": "needs_manual_review",
            }
        )

    return sorted(
        candidates,
        key=lambda item: (item["qualification_score"], item["opportunity_count"]),
        reverse=True,
    )
