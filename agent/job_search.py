"""
Exa-powered job search agent for robotics/automation roles.
Searches job boards and scores listings against the skill profile.
"""
import os
from datetime import date

from .profile import load_profile

try:
    from exa_py import Exa
    HAS_EXA = True
except ImportError:
    HAS_EXA = False

SKILL_KEYWORDS = {
    "must": ["robotics", "automation", "engineer"],
    "strong": ["allen bradley", "plc", "ur5e", "yolov8", "docker", "ros", "computer vision", "python"],
    "bonus": ["hailo", "raspberry pi", "pytorch", "typescript", "kicad"],
}


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

    for kw in SKILL_KEYWORDS["must"]:
        if kw in text:
            score += 2
            matched.append(kw)
    for kw in SKILL_KEYWORDS["strong"]:
        if kw in text:
            score += 1.5
            matched.append(kw)
    for kw in SKILL_KEYWORDS["bonus"]:
        if kw in text:
            score += 0.5
            matched.append(kw)

    return {
        "raw_score": round(min(score, 10), 1),
        "matched_keywords": matched,
    }


def scan_jobs(exa_api_key: str = None) -> list[dict]:
    """
    Run job search queries and return scored results.
    Falls back to mock data if Exa not available.
    """
    if not exa_api_key:
        exa_api_key = os.getenv("EXA_API_KEY") or os.getenv("OPENAI_API_KEY")

    if not HAS_EXA or not exa_api_key:
        return [
            {
                "company": "Example Corp",
                "role": "Automation Engineer",
                "url": "https://example.com/jobs/1",
                "score": 8.5,
                "matched_keywords": ["automation", "python", "allen bradley"],
                "source": "mock",
                "found_date": date.today().isoformat(),
            }
        ]

    exa = Exa(exa_api_key)
    results = []
    seen_urls = set()

    for query in _queries():
        try:
            response = exa.search_and_contents(
                query,
                num_results=5,
                use_autoprompt=True,
                text={"max_characters": 500},
            )
            for r in response.results:
                if r.url in seen_urls:
                    continue
                seen_urls.add(r.url)
                scored = score_listing(r.title or "", r.text or "")
                if scored["raw_score"] >= 3:
                    results.append({
                        "company": extract_company(r.title, r.url),
                        "role": r.title or "Unknown Role",
                        "url": r.url,
                        "score": scored["raw_score"],
                        "matched_keywords": scored["matched_keywords"],
                        "source": "exa",
                        "found_date": date.today().isoformat(),
                    })
        except Exception as e:
            print(f"Job search query failed: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:10]


def extract_company(title: str, url: str) -> str:
    if not title:
        return url.split("/")[2] if url else "Unknown"
    if " at " in title:
        return title.split(" at ")[-1].strip()
    if " - " in title:
        parts = title.split(" - ")
        return parts[-1].strip() if len(parts) > 1 else title
    return title
