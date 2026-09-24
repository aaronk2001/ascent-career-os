"""
Company intelligence agent — researches companies for interview prep.
"""
from datetime import date

from .job_search import NotConfigured, exa_search
from .profile import load_profile


def research_company(company: str) -> dict:
    """Research a company for interview/application prep. Recent news needs
    EXA_API_KEY; without it `recent_news` stays empty and `news_note` says why."""
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

    year = date.today().year
    try:
        news = exa_search(f"{company} robotics automation news {year - 1} {year}", num_results=3, max_chars=300)
        results["recent_news"] = [{"title": r["title"], "url": r["url"], "snippet": r["text"][:200]} for r in news]
    except NotConfigured as e:
        results["news_note"] = str(e)
    except Exception as e:
        results["error"] = str(e)

    return results
