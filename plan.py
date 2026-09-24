"""Hour-budget learning scheduler — single source of truth for projected dates.

Each track YAML declares `active` (in the current sprint or parked until the
offer), `daily_hours`, the weekdays it runs on (`days`), and per-week
`est_hours`. Remaining weeks are walked day by day from *today* consuming
daily_hours on scheduled days; parked tracks (and `[parked]` weeks) are walked
from the offer date instead. Nothing is stored, so a slipped week just slides
the projection — no date can go stale.
"""
from datetime import date, timedelta

import registry
from agent.config import load_settings

DOW = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
DEFAULT_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
DEFAULT_EST_HOURS = 6  # per week, unless the YAML sets `default_est_hours`
DEFAULT_DAILY_HOURS = 1


def _d(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def offer_date(today=None):
    return _d(load_settings().get("offer_date")) or (today or date.today())


def sprint_start(today=None):
    return _d(load_settings().get("sprint_start")) or (today or date.today())


def is_parked_week(w):
    return bool(w.get("parked")) or str(w.get("title", "")).lstrip().lower().startswith("[parked]")


def _days(data):
    names = data.get("days") or DEFAULT_DAYS
    days = {DOW[n] for n in names if n in DOW}
    return days or {DOW[n] for n in DEFAULT_DAYS}


def _walk(weeks, start, days, daily_hours, est_default):
    """Sequentially place weeks from `start`; each consumes est_hours at
    daily_hours per scheduled day. Returns (spans, last_day)."""
    spans, cursor = {}, start
    for w in weeks:
        hours = float(w.get("est_hours") or est_default)
        while cursor.weekday() not in days:
            cursor += timedelta(days=1)
        wstart, remaining = cursor, hours
        while True:
            if cursor.weekday() in days:
                remaining -= daily_hours
            if remaining <= 0:
                break
            cursor += timedelta(days=1)
        spans[w["id"]] = {"start": wstart.isoformat(), "end": cursor.isoformat()}
        cursor += timedelta(days=1)
    return spans, cursor - timedelta(days=1)


def schedule(today=None):
    """Projected {active, parked, start, end, done, weeks{id: {start, end}},
    hours_per_week, days} per track id. Completed weeks keep their real dates
    (timeline_board reads those off the week rows); only remaining weeks are
    projected."""
    today = today or date.today()
    today = max(today, sprint_start(today))  # active tracks start on sprint day 1, not before
    offer = max(offer_date(today), today)
    out = {}
    for meta in registry.all_tracks():
        tid = meta["id"]
        data = registry.load_track(tid)
        if not data or not data.get("weeks"):
            continue
        weeks = data["weeks"]
        active = data.get("active", True)
        # floor: a zero/negative daily_hours (YAML typo) would make _walk loop forever
        daily = max(0.25, float(data.get("daily_hours") or DEFAULT_DAILY_HOURS))
        days = _days(data)
        est_default = float(data.get("default_est_hours") or DEFAULT_EST_HOURS)
        remaining = [w for w in weeks if (w.get("status") or "not_started") != "completed"]
        live = [w for w in remaining if not is_parked_week(w)]
        parked = [w for w in remaining if is_parked_week(w)]
        entry = {"active": bool(active), "parked": not active, "done": False,
                 "hours_per_week": daily * len(days),
                 "days": sorted(days), "weeks": {}}
        if not remaining:
            done_dates = [d for d in (_d(w.get("completed_at")) for w in weeks) if d]
            end = max(done_dates) if done_dates else today
            entry.update({"start": _d(data.get("started")) or end, "end": end, "done": True})
            out[tid] = entry
            continue
        cursor = (max(today, _d(data.get("started")) or today) if active else offer)
        spans, end, active_end = {}, cursor - timedelta(days=1), None
        if live:
            spans, end = _walk(live, cursor, days, daily, est_default)
            active_end = end
        if parked:
            pstart = max(offer, end + timedelta(days=1))
            pspans, end = _walk(parked, pstart, days, daily, est_default)
            spans.update(pspans)
        entry.update({"start": cursor, "end": end, "weeks": spans, "active_end": active_end})
        out[tid] = entry
    return out


def program_ends(today=None):
    """(active sprint end, full program end) from a single projection walk —
    /api/anchors needs both and used to run the whole walk twice."""
    today = today or date.today()
    sched = schedule(today)
    active = [t["active_end"] for t in sched.values()
              if t["active"] and not t["done"] and t.get("active_end")]
    full = [t["end"] for t in sched.values() if not t["done"]]
    return (max(active) if active else today, max(full) if full else today)


def program_end(today=None):
    """Projected date the active sprint tracks (non-parked weeks) complete."""
    return program_ends(today)[0]


def full_program_end(today=None):
    """Projected date every track, parked ones included, completes."""
    return program_ends(today)[1]


def tracks_for_day(today=None):
    """Active, unfinished track ids that run on this weekday (empty on Sun) and
    have started (a track with a future `started` date isn't returned early)."""
    today = today or date.today()
    return [tid for tid, t in schedule(today).items()
            if t["active"] and not t["done"] and today.weekday() in t["days"]
            and t.get("start", today) <= today]


def track_for_day(today=None):
    """First track owning today's block, or None on rest days."""
    ids = tracks_for_day(today)
    return ids[0] if ids else None
