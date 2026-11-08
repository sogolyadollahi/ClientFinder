"""Deterministic job-fit scoring based on the current candidate profile."""

from dataclasses import dataclass
import re

TARGET_ROLES = {
    "python_backend": ["python backend", "backend developer", "backend engineer", "fastapi developer"],
    "python_developer": ["python developer", "python engineer"],
    "automation": ["automation engineer", "automation developer", "workflow automation", "integration developer"],
    "early_career": ["junior", "entry level", "entry-level", "intern", "internship", "graduate", "trainee", "associate"],
}

SKILL_WEIGHTS = {
    "python": 8, "fastapi": 6, "flask": 3, "django": 3,
    "rest api": 4, "api integration": 4, "automation": 4,
    "postgresql": 3, "sqlalchemy": 3, "sqlite": 1,
    "docker": 2, "pytest": 2, "github actions": 2,
    "jwt": 1, "linux": 1, "git": 1, "sql": 1,
}

SENIOR_TERMS = ("senior", "sr.", "lead", "staff", "principal", "architect", "manager", "head of", "director", "vp ")

@dataclass(frozen=True)
class JobFit:
    score: int
    category: str
    reasons: list[str]
    matched_skills: list[str]
    missing_skills: list[str]


def _contains(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])", text) is not None


def score_job(*, title: str, description: str = "", tags: list[str] | None = None,
              job_types: list[str] | None = None, remote: bool = False) -> JobFit:
    title_text = (title or "").lower()
    text = " ".join([title or "", description or "", " ".join(tags or []), " ".join(job_types or [])]).lower()
    reasons: list[str] = []

    if any(term in title_text for term in SENIOR_TERMS):
        return JobFit(0, "not_a_fit", ["Senior/leadership title is outside the current target level"], [], list(SKILL_WEIGHTS))

    role_points = 0
    role_label = None
    if "python" in title_text and any(x in title_text for x in ("backend", "back-end", "api")):
        role_points, role_label = 35, "Python backend role"
    elif any(x in title_text for x in ("backend developer", "backend engineer", "back-end")):
        role_points, role_label = 30, "Backend development role"
    elif "python" in title_text and any(x in title_text for x in ("developer", "engineer")):
        role_points, role_label = 29, "Python development role"
    elif any(x in title_text for x in ("automation", "integration")):
        role_points, role_label = 27, "Automation / integration role"
    elif "software engineer" in title_text or "software developer" in title_text:
        role_points, role_label = 17, "General software development role"
    if role_points:
        reasons.append(f"{role_label}: {role_points}/35")

    matched = [skill for skill in SKILL_WEIGHTS if _contains(text, skill)]
    skill_points = min(35, sum(SKILL_WEIGHTS[skill] for skill in matched))
    if matched:
        reasons.append(f"Resume skill overlap: {skill_points}/35 ({', '.join(matched)})")

    early_career = any(term in title_text for term in TARGET_ROLES["early_career"])
    seniority_points = 15 if early_career else 7
    reasons.append(f"Seniority fit: {seniority_points}/15" if early_career else "Seniority level not explicit: 7/15")

    remote_points = 10 if remote else 0
    if remote_points:
        reasons.append("Remote position: 10/10")

    job_type_text = " ".join(job_types or []).lower()
    employment_points = 5 if any(x in job_type_text for x in ("full", "contract", "intern", "part")) else 2
    reasons.append(f"Employment type: {employment_points}/5")

    score = min(100, role_points + skill_points + seniority_points + remote_points + employment_points)
    category = "strong_match" if score >= 75 else "good_match" if score >= 60 else "possible_match" if score >= 40 else "low_match"
    missing = [skill for skill in SKILL_WEIGHTS if skill not in matched]
    return JobFit(score, category, reasons, matched, missing)
