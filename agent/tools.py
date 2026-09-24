"""
Linda — career-only tool registry.

Tools fall into four groups:
  1. Web research        — tavily_search, research_job_market
  2. App state read      — get_career_state
  3. App state mutate    — add_application, update_application,
                           add_certification, update_certification,
                           add_timeline_event, add_weekly_task,
                           complete_weekly_task
  4. Career analysis     — analyze_offer, search_jobs

Every tool returns {"success": bool, "data": ...} or
                   {"success": False, "error": str}.

Schema accessor at the bottom emits Ollama / OpenAI function-calling format.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import date as _date, datetime, timezone
from pathlib import Path

import requests
import yaml

# Make the career-planner/ root importable from agent/tools.py
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import db
from .profile import load_profile
from data import load_data, save_data


def _market() -> str:
    return load_profile()["market"] or "United States"


# ── helpers ────────────────────────────────────────────────────────────────────

def _ok(data) -> dict:
    return {"success": True, "data": data}


def _err(exc) -> dict:
    return {"success": False, "error": str(exc)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_certifications(data: dict) -> list:
    if "certifications" not in data or not isinstance(data["certifications"], list):
        data["certifications"] = []
    return data["certifications"]


def _ensure_timeline(data: dict) -> list:
    if "timeline" not in data or not isinstance(data["timeline"], list):
        data["timeline"] = []
    return data["timeline"]


def _ensure_weekly_tasks(data: dict) -> list:
    if "weekly_tasks" not in data or not isinstance(data["weekly_tasks"], list):
        data["weekly_tasks"] = []
    return data["weekly_tasks"]


# ── 1. web research ────────────────────────────────────────────────────────────

def _tavily_search(query: str, num_results: int = 5,
                   search_depth: str = "basic", topic: str = "general") -> list[dict]:
    """Call Tavily Search API. Raises on missing key or HTTP error."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise ValueError(
            "TAVILY_API_KEY is not set — add it to career-planner/.env. "
            "Get a free key at https://tavily.com/"
        )
    r = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": key,
            "query": query,
            "max_results": min(int(num_results), 10),
            "search_depth": search_depth,        # "basic" | "advanced"
            "topic": topic,                      # "general" | "news"
            "include_answer": True,
        },
        timeout=20,
    )
    r.raise_for_status()
    payload = r.json()
    results = []
    if payload.get("answer"):
        results.append({"title": "Tavily summary", "url": "", "text": payload["answer"]})
    for x in payload.get("results", []):
        results.append({
            "title": x.get("title"),
            "url": x.get("url"),
            "text": (x.get("content") or "")[:1500],
            "score": x.get("score"),
        })
    return results


def _tavily_search_tool(inp: dict) -> dict:
    try:
        return _ok(_tavily_search(
            query=inp["query"],
            num_results=int(inp.get("num_results", 5)),
            search_depth=inp.get("search_depth", "basic"),
            topic=inp.get("topic", "general"),
        ))
    except Exception as e:
        return _err(e)


def _research_job_market(inp: dict) -> dict:
    """Targeted job-market query. Wraps Tavily with focus-specific phrasing."""
    try:
        role = (inp.get("role") or "").strip()
        if not role:
            return _err(ValueError("role is required"))
        location = inp.get("location") or _market()
        year = inp.get("year") or _date.today().year
        focus = inp.get("focus") or "salary"

        if focus == "salary":
            query = (f"{role} salary range {location} {year} "
                     f"site:levels.fyi OR site:glassdoor.com OR site:builtin.com OR site:payscale.com")
        elif focus == "demand":
            query = f"{role} job market demand hiring trends {location} {year}"
        elif focus == "skills":
            query = f"{role} required skills qualifications job description {year}"
        elif focus == "companies":
            query = f"companies hiring {role} {location} {year}"
        else:
            query = f"{role} {focus} {location} {year}"

        return _tavily_search_tool({
            "query": query,
            "num_results": int(inp.get("num_results", 5)),
            "topic": "general" if focus != "demand" else "news",
        })
    except Exception as e:
        return _err(e)


# ── 2. app state read ──────────────────────────────────────────────────────────

def _get_career_state(_inp: dict) -> dict:
    """One-shot dump of the user's job-search state. Always cheap to call."""
    try:
        data = load_data() or {}
        meta = data.get("meta") or {}
        goals = data.get("goals") or {}
        certs = data.get("certifications") or []
        timeline = data.get("timeline") or []
        weekly = data.get("weekly_tasks") or []
        skills = data.get("skills") or []

        apps = db.get_all()
        stats = db.get_stats()

        # Derive helpful summaries instead of raw blobs
        return _ok({
            "summary": {
                "current_phase": meta.get("current_phase", 1),
                "current_week": meta.get("current_week"),
                "target_salary_phase1": meta.get("target_salary_p1"),
                "target_salary_phase3": meta.get("target_salary_p3"),
                "applications_total": stats.get("total", 0),
                "applications_by_stage": stats.get("by_stage", {}),
                "overdue_followups": stats.get("overdue_count", 0),
                "this_week_count": stats.get("this_week_count", 0),
                "response_rate_pct": stats.get("response_rate", 0),
                "certifications_total": len(certs),
                "timeline_events_total": len(timeline),
                "open_tasks_total": len([t for t in weekly if t.get("status") != "done"]),
            },
            "applications": apps,
            "goals": {
                "phases": goals.get("phases", []),
                "weekly_actions": goals.get("weekly_actions", []),
                "skill_gaps": goals.get("skill_gaps", []),
            },
            "skills": skills,
            "certifications": certs,
            "timeline": timeline,
            "weekly_tasks": weekly,
        })
    except Exception as e:
        return _err(e)


# ── 3. app state mutate ────────────────────────────────────────────────────────

def _add_application(inp: dict) -> dict:
    try:
        company = (inp.get("company") or "").strip()
        role = (inp.get("role") or "").strip()
        if not company or not role:
            return _err(ValueError("company and role are required"))
        record = db.create({
            "company": company,
            "role": role,
            "status": inp.get("status") or "discovered",
            "score": inp.get("score"),
            "url": inp.get("url"),
            "salary_range": inp.get("salary_range"),
            "contact_name": inp.get("contact_name"),
            "contact_email": inp.get("contact_email"),
            "follow_up_date": inp.get("follow_up_date"),
            "resume_variant": inp.get("resume_variant"),
            "notes": inp.get("notes"),
        })
        return _ok({"added": record})
    except Exception as e:
        return _err(e)


def _update_application(inp: dict) -> dict:
    try:
        app_id = (inp.get("id") or "").strip()
        if not app_id:
            return _err(ValueError("id is required"))
        # Whitelist fields to prevent stomping created_at/id
        allowed = {"company", "role", "status", "score", "url", "salary_range",
                   "contact_name", "contact_email", "applied_date",
                   "follow_up_date", "resume_variant", "notes", "interview_notes"}
        patch = {k: v for k, v in inp.items() if k in allowed}
        if not patch:
            return _err(ValueError("no valid fields to update"))
        record = db.update(app_id, patch)
        if not record:
            return _err(ValueError(f"application not found: {app_id}"))
        return _ok({"updated": record})
    except Exception as e:
        return _err(e)


def _add_certification(inp: dict) -> dict:
    try:
        title = (inp.get("title") or "").strip()
        if not title:
            return _err(ValueError("title is required"))
        data = load_data() or {}
        certs = _ensure_certifications(data)
        cert = {
            "id": f"cert_{uuid.uuid4().hex[:8]}",
            "provider": (inp.get("provider") or "").strip(),
            "title": title,
            "url": (inp.get("url") or "").strip(),
            "track": (inp.get("track") or "general").strip(),
            "status": inp.get("status") or "wishlist",
            "hours": inp.get("hours"),
            "cost": inp.get("cost"),
            "notes": inp.get("notes"),
            "created_at": _now_iso(),
        }
        certs.append(cert)
        save_data(data)
        return _ok({"added": cert})
    except Exception as e:
        return _err(e)


def _update_certification(inp: dict) -> dict:
    try:
        cert_id = (inp.get("id") or "").strip()
        if not cert_id:
            return _err(ValueError("id is required"))
        data = load_data() or {}
        certs = _ensure_certifications(data)
        for cert in certs:
            if cert.get("id") == cert_id:
                for k, v in inp.items():
                    if k != "id":
                        cert[k] = v
                cert["updated_at"] = _now_iso()
                save_data(data)
                return _ok({"updated": cert})
        return _err(ValueError(f"certification not found: {cert_id}"))
    except Exception as e:
        return _err(e)


def _add_timeline_event(inp: dict) -> dict:
    try:
        label = (inp.get("label") or "").strip()
        event_date = (inp.get("date") or "").strip()
        if not label:
            return _err(ValueError("label is required"))
        if not _DATE_RE.fullmatch(event_date):
            return _err(ValueError("date must be YYYY-MM-DD"))
        data = load_data() or {}
        events = _ensure_timeline(data)
        event = {
            "id": f"tl_{uuid.uuid4().hex[:8]}",
            "date": event_date,
            "kind": inp.get("kind") or "milestone",
            "label": label,
            "phase": inp.get("phase"),
            "track": inp.get("track"),
            "done": bool(inp.get("done", False)),
            "notes": inp.get("notes"),
        }
        events.append(event)
        save_data(data)
        return _ok({"added": event})
    except Exception as e:
        return _err(e)


def _add_weekly_task(inp: dict) -> dict:
    try:
        text = (inp.get("text") or "").strip()
        if not text:
            return _err(ValueError("text is required"))
        data = load_data() or {}
        tasks = _ensure_weekly_tasks(data)
        new_task = {
            "id": f"t{int(time.time() * 1000) % 999999:06d}",
            "task": text,
            "status": "pending",
            "priority": inp.get("priority") or "medium",
            "week": (data.get("meta") or {}).get("current_week", 1),
        }
        tasks.append(new_task)
        save_data(data)
        return _ok({"added": new_task})
    except Exception as e:
        return _err(e)


def _complete_weekly_task(inp: dict) -> dict:
    try:
        task_id = (inp.get("id") or "").strip()
        text_match = (inp.get("text") or "").strip().lower()
        if not task_id and not text_match:
            return _err(ValueError("id or text is required"))
        data = load_data() or {}
        tasks = _ensure_weekly_tasks(data)
        for t in tasks:
            label = t.get("task") or t.get("text") or ""
            if (task_id and t.get("id") == task_id) or \
               (text_match and text_match in label.lower()):
                t["status"] = "done"
                save_data(data)
                return _ok({"completed": t})
        return _err(ValueError(f"task not found: {task_id or text_match}"))
    except Exception as e:
        return _err(e)


# ── 4. career analysis ─────────────────────────────────────────────────────────

def _analyze_offer(inp: dict) -> dict:
    """Offer math. Decoupled from financial_snapshot — Linda is career-only.
    Missing current_salary / target / monthly_burn fall back to profile.yaml.
    """
    try:
        offer = float(inp["offer"])
        prof = load_profile()
        current = float(inp.get("current_salary") or prof["current_salary"] or 0)
        title = inp.get("title") or ""
        gap_weeks = int(inp.get("gap_weeks") or 0)
        # target band from the profile; without one, a 25% raise is the bar
        target_p1 = float(prof["target_salary"] or (current * 1.25 if current else offer))

        def net_monthly(gross: float) -> float:
            # Rough 74 % after-tax for AZ, ~$65–115k bracket
            return round(gross * 0.74 / 12, 0)

        current_take = net_monthly(current)
        offer_take = net_monthly(offer)
        delta = offer_take - current_take
        # gap cost from the profile's monthly expenses; caller can override via `monthly_burn`
        monthly_burn = float(inp.get("monthly_burn") or prof["monthly_expenses"] or 0)
        gap_cost = round(monthly_burn * gap_weeks / 4.33) if gap_weeks else 0
        months_to_recover = round(gap_cost / delta, 1) if delta > 0 and gap_cost else 0

        counter_low = round((offer * 1.10) / 5000) * 5000
        counter_high = round((offer * 1.15) / 5000) * 5000

        pct_above_current = round((offer - current) / current * 100, 1) if current else 0.0
        hits_p1_target = offer >= target_p1 * 0.95

        verdict = (
            "STRONG YES" if offer >= target_p1
            else "YES" if offer >= target_p1 * 0.90
            else "NEGOTIATE" if offer >= current * 1.10
            else "NO"
        )

        return _ok({
            "offer": offer,
            "title": title,
            "verdict": verdict,
            "current_salary": current,
            "pct_above_current": pct_above_current,
            "hits_phase1_target": hits_p1_target,
            "take_home": {
                "current_monthly": current_take,
                "offer_monthly": offer_take,
                "monthly_delta": delta,
                "annual_delta": round(delta * 12),
            },
            "gap_analysis": {
                "gap_weeks": gap_weeks,
                "gap_cost": gap_cost,
                "months_to_recover": months_to_recover,
            },
            "negotiation": {
                "counter_low": counter_low,
                "counter_high": counter_high,
                "recommended_counter": counter_high if verdict == "NEGOTIATE" else counter_low,
                "rationale": (
                    f"Market for {title or 'this role'} supports "
                    f"${counter_low:,.0f}–${counter_high:,.0f}. Always counter once."
                ),
            },
        })
    except Exception as e:
        return _err(e)


def _linda_remember(inp: dict) -> dict:
    """Persist a snippet to Linda's RAG memory. Lazy-imports rag module."""
    try:
        from . import rag
        text = (inp.get("text") or "").strip()
        tag = (inp.get("tag") or "general").strip()
        if not text:
            return _err(ValueError("text is required"))
        return _ok(rag.remember(text, tag))
    except Exception as e:
        return _err(e)


def _linda_search_memory(inp: dict) -> dict:
    """Search Linda's RAG memory for relevant past snippets / corpus."""
    try:
        from . import rag
        query = (inp.get("query") or "").strip()
        if not query:
            return _err(ValueError("query is required"))
        return _ok(rag.search(
            query,
            k=int(inp.get("k", 5)),
            tag_filter=inp.get("tag_filter"),
        ))
    except Exception as e:
        return _err(e)


def _search_jobs(inp: dict) -> dict:
    """Search Indeed via the sibling job-search-agent scraper.
    Falls back with guidance if the scraper isn't available on this box."""
    try:
        query = inp.get("query") or "controls engineer"
        location = inp.get("location") or _market()
        pages = min(int(inp.get("pages", 2)), 4)
        min_salary = int(inp.get("min_salary", 0))

        scraper_path = Path(__file__).resolve().parent.parent.parent / "job-search-agent" / "src"
        if str(scraper_path) not in sys.path:
            sys.path.insert(0, str(scraper_path))

        try:
            from scrapers.indeed_scraper import search_indeed   # type: ignore
        except ImportError as e:
            return _err(ImportError(
                f"job-search-agent scraper not installed: {e}. "
                f"Try tavily_search with query: '{query} jobs {location}'"
            ))

        jobs = search_indeed(query, location=location, pages=pages)
        if min_salary:
            jobs = [
                j for j in jobs
                if j.get("salary_max", 0) >= min_salary
                or j.get("salary_min", 0) >= min_salary
            ]
        top = jobs[:10]
        summary = []
        for j in top:
            sal = ""
            if j.get("salary_min") and j.get("salary_max"):
                sal = f"${j['salary_min']//1000}k–${j['salary_max']//1000}k"
            elif j.get("salary_min"):
                sal = f"${j['salary_min']//1000}k+"
            summary.append({
                "title": j.get("title") or "",
                "company": j.get("company") or "",
                "location": j.get("location") or "",
                "salary": sal or "Not listed",
                "url": j.get("url") or "",
            })
        return _ok({"count": len(jobs), "top": summary, "query": query, "location": location})
    except Exception as e:
        return _err(e)


# ── registry ───────────────────────────────────────────────────────────────────

import re as _re
_DATE_RE = _re.compile(r"\d{4}-\d{2}-\d{2}")

TOOLS: list[dict] = [
    # 1. web research ──────────────────────────────────────────────────────────
    {
        "name": "tavily_search",
        "description": (
            "Web search via Tavily API. Use for open-ended career and industry "
            "questions: company culture, certification programs, interview prep, "
            "market trends, recruiter advice. Returns a concise summary plus the "
            "top sources. Prefer this over generic guesses — Linda should cite."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":        {"type": "string", "description": "What to search for"},
                "num_results":  {"type": "integer", "description": "1–10, default 5"},
                "search_depth": {"type": "string", "enum": ["basic", "advanced"], "description": "basic = fast; advanced = deeper"},
                "topic":        {"type": "string", "enum": ["general", "news"], "description": "news for breaking events"},
            },
            "required": ["query"],
        },
        "execute": _tavily_search_tool,
    },
    {
        "name": "research_job_market",
        "description": (
            "Targeted job-market research: salary, hiring demand, required skills, "
            "or companies hiring. Wraps tavily_search with focus-specific phrasing. "
            "Default location comes from the user profile."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "role":     {"type": "string", "description": "Job title, e.g. 'Controls Engineer II'"},
                "location": {"type": "string", "description": "City, state. Defaults to the profile market"},
                "focus":    {"type": "string", "enum": ["salary", "demand", "skills", "companies"]},
                "year":     {"type": "integer", "description": "Year context (defaults to current)"},
                "num_results": {"type": "integer"},
            },
            "required": ["role"],
        },
        "execute": _research_job_market,
    },
    # 2. app state read ────────────────────────────────────────────────────────
    {
        "name": "get_career_state",
        "description": (
            "One-shot dump of the user's current job-search state: applications and "
            "stats, goals, skill gaps, certifications, timeline events, weekly "
            "tasks, phase metadata. Always cheap — call this first when the "
            "question is 'where am I' or 'what's overdue' or 'what's on my plate'."
        ),
        "input_schema": {"type": "object", "properties": {}},
        "execute": _get_career_state,
    },
    # 3. app state mutate ──────────────────────────────────────────────────────
    {
        "name": "add_application",
        "description": (
            "Add a new job application to the user's tracker. company and role are "
            "required. Status defaults to 'discovered'. Use when the user says "
            "'add this job' or pastes a posting."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company":        {"type": "string"},
                "role":           {"type": "string"},
                "status":         {"type": "string", "enum": ["discovered", "applied", "phone_screen", "technical", "onsite", "offer", "rejected"]},
                "score":          {"type": "number", "description": "Fit score 0–10"},
                "url":            {"type": "string"},
                "salary_range":   {"type": "string"},
                "contact_name":   {"type": "string"},
                "contact_email":  {"type": "string"},
                "follow_up_date": {"type": "string", "description": "YYYY-MM-DD"},
                "resume_variant": {"type": "string"},
                "notes":          {"type": "string"},
            },
            "required": ["company", "role"],
        },
        "execute": _add_application,
    },
    {
        "name": "update_application",
        "description": (
            "Update an existing application by id. Common updates: status "
            "(advance pipeline stage), score, follow_up_date, notes, "
            "interview_notes. Field 'id' must be the app_id e.g. 'app_a1b2c3d4'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id":              {"type": "string"},
                "status":          {"type": "string"},
                "score":           {"type": "number"},
                "follow_up_date":  {"type": "string"},
                "applied_date":    {"type": "string"},
                "salary_range":    {"type": "string"},
                "contact_name":    {"type": "string"},
                "contact_email":   {"type": "string"},
                "resume_variant":  {"type": "string"},
                "notes":           {"type": "string"},
                "interview_notes": {"type": "string"},
            },
            "required": ["id"],
        },
        "execute": _update_application,
    },
    {
        "name": "add_certification",
        "description": (
            "Add a certification to the user's tracker. status defaults to 'wishlist'. "
            "track is one of: controls, ml, robotics, cloud, embedded, general."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title":    {"type": "string"},
                "provider": {"type": "string"},
                "url":      {"type": "string"},
                "track":    {"type": "string"},
                "status":   {"type": "string", "enum": ["wishlist", "in_progress", "completed", "later", "cut"]},
                "hours":    {"type": "number"},
                "cost":     {"type": "number"},
                "notes":    {"type": "string"},
            },
            "required": ["title"],
        },
        "execute": _add_certification,
    },
    {
        "name": "update_certification",
        "description": "Update an existing certification by id (e.g. 'cert_a1b2c3d4').",
        "input_schema": {
            "type": "object",
            "properties": {
                "id":     {"type": "string"},
                "status": {"type": "string", "enum": ["wishlist", "in_progress", "completed", "later", "cut"]},
                "hours":  {"type": "number"},
                "notes":  {"type": "string"},
            },
            "required": ["id"],
        },
        "execute": _update_certification,
    },
    {
        "name": "add_timeline_event",
        "description": (
            "Add a milestone, deadline, exam date, submission, or interview to "
            "the user's career timeline. Date is YYYY-MM-DD. kind defaults to 'milestone'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date":  {"type": "string", "description": "YYYY-MM-DD"},
                "label": {"type": "string"},
                "kind":  {"type": "string", "enum": ["milestone", "deadline", "exam", "submission", "review", "interview"]},
                "phase": {"type": "string"},
                "track": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["date", "label"],
        },
        "execute": _add_timeline_event,
    },
    {
        "name": "add_weekly_task",
        "description": "Add a task to the user's current-week task list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text":     {"type": "string"},
                "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
            },
            "required": ["text"],
        },
        "execute": _add_weekly_task,
    },
    {
        "name": "complete_weekly_task",
        "description": "Mark a weekly task done by id or by text substring match.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id":   {"type": "string"},
                "text": {"type": "string", "description": "Substring of task text to match"},
            },
        },
        "execute": _complete_weekly_task,
    },
    # 4. career analysis ───────────────────────────────────────────────────────
    {
        "name": "analyze_offer",
        "description": (
            "Analyze a job offer. Returns verdict (STRONG YES / YES / NEGOTIATE / "
            "NO), take-home delta, optional gap-cost recovery, and counter-offer "
            "range. Decoupled from finance app — current_salary defaults to the "
            "saved profile value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "offer":          {"type": "number", "description": "Annual base in dollars"},
                "title":          {"type": "string"},
                "current_salary": {"type": "number", "description": "Defaults to the profile value"},
                "gap_weeks":      {"type": "integer", "description": "Weeks without pay; 0 if none"},
                "monthly_burn":   {"type": "number", "description": "Monthly expense estimate; defaults to the profile value"},
            },
            "required": ["offer"],
        },
        "execute": _analyze_offer,
    },
    {
        "name": "search_jobs",
        "description": (
            "Search Indeed via the local job-search-agent scraper. Returns up to "
            "10 listings with title, company, location, salary, and URL. "
            "Falls back with guidance if scraper isn't on the box."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":      {"type": "string"},
                "location":   {"type": "string"},
                "pages":      {"type": "integer", "description": "1–4"},
                "min_salary": {"type": "integer"},
            },
            "required": ["query"],
        },
        "execute": _search_jobs,
    },
    # 5. RAG memory ────────────────────────────────────────────────────────────
    {
        "name": "linda_remember",
        "description": (
            "Persist a snippet to Linda's local memory store so future "
            "conversations can recall it. Use when the user explicitly asks Linda "
            "to remember something ('Linda, remember that I prefer hardware "
            "over pure software roles'), or when Linda has reached a useful "
            "conclusion worth keeping. Tag with a short category like "
            "'preferences', 'companies', 'interview-feedback'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Snippet to persist"},
                "tag":  {"type": "string", "description": "Category tag (default 'general')"},
            },
            "required": ["text"],
        },
        "execute": _linda_remember,
    },
    {
        "name": "linda_search_memory",
        "description": (
            "Search Linda's local memory + corpus for snippets relevant to a "
            "query. Returns top-k matches by semantic similarity. Use when "
            "answering would benefit from context Linda has stored — past "
            "preferences, prior interview feedback, ingested resume / plan docs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":      {"type": "string"},
                "k":          {"type": "integer", "description": "Top-k, max 10"},
                "tag_filter": {"type": "string", "description": "Restrict to a tag"},
            },
            "required": ["query"],
        },
        "execute": _linda_search_memory,
    },
]


# ── accessors ──────────────────────────────────────────────────────────────────

def get_all_tools() -> list[dict]:
    return TOOLS


def get_tool(name: str) -> dict | None:
    return next((t for t in TOOLS if t["name"] == name), None)


def get_ollama_schemas() -> list[dict]:
    """Ollama / OpenAI function-calling schema format."""
    return [
        {
            "type": "function",
            "function": {
                "name":        t["name"],
                "description": t["description"],
                "parameters":  t["input_schema"],
            },
        }
        for t in TOOLS
    ]


def get_anthropic_schemas() -> list[dict]:
    """Anthropic tool-use schema format (registry is already native)."""
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        for t in TOOLS
    ]
