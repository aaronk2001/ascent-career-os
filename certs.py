"""Cert study pace + budget math. `db` owns rows; Today and the Certs view both
read pace from here so they can't disagree."""
from datetime import date, timedelta

ACTIVE = "in_progress"
SLOT_HOURS = 0.75  # the 45-min Today cert block, Mon-Sat


def _d(s):
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def next_study_cert(rows, today=None):
    """Today's cert pick, shared by dayplan._fill_cert and focus.compute so they
    can't disagree: in_progress certs with an unchecked step, soonest exam_date
    first (nulls last)."""
    open_ = [c for c in rows if c.get("status") == ACTIVE and any(not s["done"] for s in c.get("steps") or [])]
    if not open_:
        return None
    return sorted(open_, key=lambda c: (c.get("exam_date") or "9999-12-31", c.get("sort") or 0))[0]


def pace(cert, today):
    steps = cert.get("steps") or []
    hours_left = round(sum(s["hours"] for s in steps if not s.get("done")), 2)
    out = {"days_left": None, "hours_left": hours_left, "slot_hours": 0.0}
    if not steps:
        return {**out, "state": "no_plan"}
    if all(s.get("done") for s in steps):
        return {**out, "state": "done"}
    exam = _d(cert.get("exam_date"))
    if not exam:
        return {**out, "state": "no_date"}
    if exam < today:
        return {**out, "days_left": (exam - today).days, "state": "past"}
    slots = sum(1 for i in range((exam - today).days)
                if (today + timedelta(days=i)).weekday() < 6)
    slot_hours = round(slots * SLOT_HOURS, 2)
    state = "on_pace" if hours_left <= slot_hours else "behind"
    return {**out, "days_left": (exam - today).days, "slot_hours": slot_hours, "state": state}


def budget(rows, runway_end, cert_budget):
    active = [r for r in rows if r.get("status") == ACTIVE]
    total = float(sum(r.get("cost_usd") or 0 for r in active))
    end = _d(runway_end)
    before = float(sum(r.get("cost_usd") or 0 for r in active
                       if end and _d(r.get("exam_date")) and _d(r["exam_date"]) <= end))
    pct = round(total / float(cert_budget) * 100) if cert_budget else None
    return {"active_total": total, "before_runway": before, "pct_of_budget": pct}
