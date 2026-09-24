"""
Job-posting search through the Exa REST API, scored against a keyword profile.

Optional: needs EXA_API_KEY in the environment. Only that key is ever sent, and
only to api.exa.ai. Without it every entry point returns a "not configured"
result instead of data, so nothing fake reaches the UI or Linda.
"""
import os
from datetime import date

import requests

from .profile import load_profile

EXA_URL = "https://api.exa.ai/search"
NOT_CONFIGURED = "Job search is not configured: set EXA_API_KEY in .env (get a key at exa.ai)."

SKILL_KEYWORDS = {
    "must": ["robotics", "automation", "engineer"],
    "strong": ["allen bradley", "plc", "ur5e", "yolov8", "docker", "ros", "computer vision", "python"],
    "bonus": ["hailo", "raspberry pi", "pytorch", "typescript", "kicad"],
}


class NotConfigured(RuntimeError):
    pass


def exa_search(query: str, num_results: int = 5, max_chars: int = 500) -> list[dict]:
    """[{title, url, text}] from Exa. Raises NotConfigured without EXA_API_KEY."""
    key = os.environ.get("EXA_API_KEY", "").strip()
    if not key:
        raise NotConfigured(NOT_CONFIGURED)
    r = requests.post(
        EXA_URL,
        headers={"x-api-key": key},
        json={"query": query, "numResults": int(num_results),
              "contents": {"text": {"maxCharacters": int(max_chars)}}},
        timeout=20,
    )
    r.raise_for_status()
    return [{"title": x.get("title") or "", "url": x.get("url") or "", "text": x.get("text") or ""}
            for x in r.json().get("results", [])]


def _queries() -> list[str]:
    m = load_profile()["market"] or "United States"
    return [
        f"robotics engineer jobs {m} {date.today().year}",
        f"automation engineer controls engineer {m} hiring",
        f"PLC Allen Bradley engineer jobs {m}",
        f"computer vision ML engineer robotics {m}",
    ]


def score_listing(title: str, description: str) -> dict:
    text = (title + " " + description).lower()
    score = 0
    matched = []
    for tier, pts in (("must", 2), ("strong", 1.5), ("bonus", 0.5)):
        for kw in SKILL_KEYWORDS[tier]:
            if kw in text:
                score += pts
                matched.append(kw)
    return {"raw_score": round(min(score, 10), 1), "matched_keywords": matched}


def scan_jobs(queries: list[str] | None = None, min_score: float = 3, limit: int = 10) -> dict:
    """{ok, jobs, errors} for the profile's default queries (or `queries`).
    {ok: False, error} when Exa is not configured."""
    if not os.environ.get("EXA_API_KEY", "").strip():
        return {"ok": False, "error": NOT_CONFIGURED, "jobs": []}
    results, seen, errors = [], set(), []
    for query in queries or _queries():
        try:
            hits = exa_search(query)
        except Exception as e:
            errors.append(f"{query}: {e}")
            continue
        for r in hits:
            if not r["url"] or r["url"] in seen:
                continue
            seen.add(r["url"])
            scored = score_listing(r["title"], r["text"])
            if scored["raw_score"] >= min_score:
                results.append({
                    "company": extract_company(r["title"], r["url"]),
                    "role": r["title"] or "Unknown Role",
                    "url": r["url"],
                    "score": scored["raw_score"],
                    "matched_keywords": scored["matched_keywords"],
                    "source": "exa",
                    "found_date": date.today().isoformat(),
                })
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"ok": True, "jobs": results[:limit], "errors": errors}


def extract_company(title: str, url: str) -> str:
    if not title:
        return url.split("/")[2] if url else "Unknown"
    if " at " in title:
        return title.split(" at ")[-1].strip()
    if " - " in title:
        parts = title.split(" - ")
        return parts[-1].strip() if len(parts) > 1 else title
    return title
