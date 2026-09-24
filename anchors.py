"""Single source of truth for the plan's headline dates.

Sprint anchors (offer / stretch / runway / bridge gate) come from settings.yaml;
the next cert exam, projected sprint end and primary-goal milestone are derived
live from career.db + the track registry, so every section (Timeline, Dashboard,
Focus, Today, morning brief) shows the same dates.
"""
from datetime import date

import db
import plan
from agent.config import load_settings


def _iso(s):
    return str(s)[:10] if s else None


def _d(s):
    try:
        return date.fromisoformat(_iso(s))
    except (TypeError, ValueError):
        return None


def plan_anchors():
    today = date.today()
    today_iso = today.isoformat()
    s = load_settings()
    exams = sorted(
        (_iso(c["exam_date"]), c["title"])
        for c in db.certs_all()
        if c.get("exam_date") and c.get("status") not in ("completed", "later", "cut")
        and _iso(c["exam_date"]) >= today_iso
    )
    primary = sorted(
        (m for m in db.milestones_all()
         if m.get("due") and not m.get("done")
         and "(primary goal)" in (m.get("text") or "").lower()),
        key=lambda m: m["due"],
    )
    runway = _d(s.get("runway_end"))
    offer = _d(s.get("offer_date"))
    prog_end, full_end = plan.program_ends(today)
    return {
        "next_exam": exams[0][0] if exams else None,
        "next_exam_title": exams[0][1] if exams else None,
        "program_end": prog_end.isoformat(),
        "full_program_end": full_end.isoformat(),
        "primary_due": _iso(primary[0]["due"]) if primary else None,
        "primary_text": primary[0]["text"] if primary else None,
        "sprint_start": _iso(s.get("sprint_start")),
        "sprint_days": (today - _d(s.get("sprint_start"))).days if _d(s.get("sprint_start")) else None,
        "offer_date": _iso(s.get("offer_date")),
        "stretch_date": _iso(s.get("stretch_date")),
        "runway_end": _iso(s.get("runway_end")),
        "bridge_gate": _iso(s.get("bridge_gate")),
        "bridge_mode": bool(s.get("bridge_mode")),
        "runway_days": (runway - today).days if runway else None,
        "offer_days": (offer - today).days if offer else None,
    }


def deadline():
    """Working deadline for backend day-count math (Focus ranking, morning
    brief): the offer date, else the next exam, else projected sprint end."""
    a = plan_anchors()
    for key in ("offer_date", "next_exam", "program_end"):
        d = _d(a.get(key))
        if d:
            return d
    return date.today()
