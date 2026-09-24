"""
Company intelligence agent — researches companies for interview prep.
"""
import os

from .profile import load_profile

try:
    from exa_py import Exa
    HAS_EXA = True
except ImportError:
    HAS_EXA = False


def research_company(company: str, exa_api_key: str = None) -> dict:
    """Research a company for interview/application prep."""

    if not exa_api_key:
        exa_api_key = os.getenv("EXA_API_KEY")

    results = {
        "company": company,
        "summary": f"Research for {company}",
        "recent_news": [],
        "glassdoor_signals": "Search Glassdoor for reviews",
        "tech_stack": "Research their job postings for tech stack clues",
        "talking_points": [t.replace("{company}", company) for t in load_profile()["talking_points"]] or [
            f"Connect your most relevant shipped project to {company}'s products",
            "Highlight the tools from the job posting you have already used in production",
        ],
        "salary_range": "Check levels.fyi and LinkedIn Salary for current ranges",
        "red_flags": [],
    }

    if HAS_EXA and exa_api_key:
        try:
            exa = Exa(exa_api_key)
            news = exa.search_and_contents(
                f"{company} robotics automation news 2025 2026",
                num_results=3,
                text={"max_characters": 300},
            )
            results["recent_news"] = [
                {"title": r.title, "url": r.url, "snippet": (r.text or "")[:200]}
                for r in news.results
            ]
        except Exception as e:
            results["error"] = str(e)

    return results
