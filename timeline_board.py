"""Unified timeline board — server-side aggregation for the Gantt view.

Collapses every dated thing in the app (learning-track weeks, cert exams,
milestones, job applications + follow-ups, weekly actions) into a single flat
`items` list with a `lane` + `source`, plus derived countdown `anchors`,
per-lane `health`, and a `triage` list of stale/overdue rows.

The frontend `/api/timeline/board` handler just calls `board()`.
Dates are handled as `YYYY-MM-DD` strings throughout — no tz math.
"""
from datetime import date, datetime, timedelta, timezone

import anchors
import db
import plan
import registry

# Lane order is the row order in the Gantt (top → bottom). Learning leads —
# it's the primary goal.
LANES = ["learning", "certs", "milestones", "applications", "follow-ups", "weekly", "events"]

# Which lanes write back to a source table on drag (see interact.ts sync map).
_EDITABLE_SOURCES = {"timeline", "milestone", "followup", "cert"}


def _d(s):
    """Parse a YYYY-MM-DD(...) string to a date, or None."""
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _iso(d):
    return d.isoformat() if d else None


def _item(lane, source, source_id, date_str, label, *, done=False, end_date=None,
          phase=None, track=None, editable=None, meta=None):
    return {
        "id": f"{source}:{source_id}",
        "lane": lane,
        "source": source,
        "source_id": source_id,
        "date": (date_str or "")[:10],
        "end_date": (end_date or None) and end_date[:10],
        "label": label,
        "done": bool(done),
        "phase": phase,
        "track": track,
        "editable": _EDITABLE_SOURCES.__contains__(source) if editable is None else editable,
        "meta": meta or {},
    }


def _collect(items, today):
    """Populate `items` from every source table. `today` is a date."""
    today_iso = today.isoformat()

    # ── ad-hoc events (timeline_events) ────────────────────────────────────────
    for e in db.timeline_all():
        if not e.get("date"):
            continue
        items.append(_item("events", "timeline", e["id"], e["date"], e["label"],
                           done=bool(e.get("done")), phase=e.get("phase"), track=e.get("track"),
                           meta={"kind": e.get("kind"), "notes": e.get("notes")}))

    # ── milestones (incl. financial goals) ─────────────────────────────────────
    for m in db.milestones_all():
        if not m.get("due"):
            continue
        items.append(_item("milestones", "milestone", m["id"], m["due"], m["text"],
                           done=bool(m.get("done")), phase=m.get("phase"),
                           meta={"anchor": "(primary goal)" in (m["text"] or "").lower()}))

    # ── job applications: applied (locked history) + follow-ups (editable) ─────
    for a in db.get_all():
        if a.get("applied_date"):
            items.append(_item("applications", "application", a["id"], a["applied_date"],
                               f"Applied · {a['company']}", done=True, editable=False,
                               meta={"role": a.get("role"), "bucket": a.get("bucket"),
                                     "status": a.get("status")}))
        due = a.get("next_action_due") or a.get("follow_up_date")
        if due and a.get("status") not in ("offer", "rejected", "archived"):
            items.append(_item("follow-ups", "followup", a["id"], due,
                               f"Follow up · {a['company']}",
                               done=False,
                               meta={"role": a.get("role"), "bucket": a.get("bucket"),
                                     "overdue": due[:10] < today_iso,
                                     "field": "next_action_due" if a.get("next_action_due") else "follow_up_date"}))

    # ── certifications with a scheduled exam date ──────────────────────────────
    for c in db.certs_all():
        if not c.get("exam_date") or c.get("status") in ("completed", "later", "cut"):
            continue
        items.append(_item("certs", "cert", c["id"], c["exam_date"],
                           f"Exam · {c['title']}", done=False,
                           track=c.get("track"),
                           meta={"provider": c.get("provider"), "status": c.get("status")}))

    # ── learning-track weeks as bars (rolling projection from plan.py) ─────────
    sched = plan.schedule(today)
    for meta in registry.all_tracks():
        _collect_track_weeks(items, meta["id"], sched)

    # ── weekly action items (keyed by week-of Monday); done-toggle only ────────
    for w in db.weekly_all():
        if not w.get("week"):
            continue
        items.append(_item("weekly", "weekly", w["id"], w["week"], w["text"],
                           done=bool(w.get("done")), editable=False))


def _collect_track_weeks(items, tid, sched):
    """One bar per curriculum week. Completed weeks keep their real
    started_at/completed_at; remaining weeks use the rolling projection from
    plan.schedule() (anchored to today — never stale)."""
    data = registry.load_track(tid)
    if not data:
        return
    weeks = data.get("weeks", [])
    if not weeks:
        return
    proj = (sched.get(tid) or {}).get("weeks", {})
    short = registry.short_name(tid, data)
    parked = not data.get("active", True)
    for w in weeks:
        status = w.get("status") or "not_started"
        p = proj.get(w["id"]) or {}
        start = _d(w.get("started_at")) or _d(p.get("start"))
        end = _d(w.get("completed_at")) or _d(p.get("end"))
        if not start and not end:
            continue
        start = start or end
        end = end or start
        if end < start:
            end = start
        items.append(_item("learning", "track", f"{tid}#{w['id']}",
                           start.isoformat(), f"{short} W{w['id']}: {w.get('title', '')}",
                           done=(status == "completed"), end_date=end.isoformat(),
                           editable=False, track=tid,
                           meta={"status": status, "week_id": w["id"], "parked": parked}))


def _rung(*, on, at):
    """Pick a status from two boolean thresholds (on_track wins, then at_risk)."""
    return "on_track" if on else ("at_risk" if at else "behind")


def _health(items, today):
    """Per-lane on_track / at_risk / behind, each with a short human detail."""
    today_iso = today.isoformat()
    out = {}

    # applications — this week's volume vs pro-rated weekly target
    try:
        cad = db.get_cadence()
        target = sum((cad.get("bucket_targets") or {}).values()) or cad.get("weekly_target") or 15
        prorata = max(target * (today.weekday() + 1) / 7.0, 1)
        got = cad.get("week_total", 0)
        ratio = got / prorata
        out["applications"] = {"status": _rung(on=ratio >= 1, at=ratio >= 0.5),
                               "detail": f"{got}/{target} apps this week",
                               "metrics": {"week_total": got, "target": target}}
        overdue_fu = sum(1 for n in cad.get("needs_followup", []) if n.get("overdue"))
        out["follow-ups"] = {"status": _rung(on=overdue_fu == 0, at=overdue_fu <= 2),
                             "detail": f"{overdue_fu} overdue" if overdue_fu else "all current",
                             "metrics": {"overdue": overdue_fu}}
    except Exception:
        pass

    # milestones — overdue undone count
    ms_over = sum(1 for i in items if i["lane"] == "milestones" and not i["done"] and i["date"] < today_iso)
    out["milestones"] = {"status": _rung(on=ms_over == 0, at=ms_over <= 2),
                         "detail": f"{ms_over} overdue" if ms_over else "on plan",
                         "metrics": {"overdue": ms_over}}

    # certs — overdue exams / exams looming without prep
    cbehind = catrisk = 0
    for c in db.certs_all():
        ed = c.get("exam_date")
        if not ed or c.get("status") in ("completed", "later", "cut"):
            continue
        days = (date.fromisoformat(ed[:10]) - today).days if _d(ed) else None
        if days is None:
            continue
        if days < 0:
            cbehind += 1
        elif days <= 14 and c.get("status") != "in_progress":
            catrisk += 1
    if any(c.get("exam_date") for c in db.certs_all()):
        out["certs"] = {"status": _rung(on=cbehind == 0 and catrisk == 0, at=cbehind == 0),
                        "detail": (f"{cbehind} exam(s) overdue" if cbehind else
                                   f"{catrisk} exam(s) soon" if catrisk else "scheduled"),
                        "metrics": {"overdue": cbehind, "soon": catrisk}}

    # learning — with rolling projections there is no "calendar-expected week";
    # health = recency of real activity on the scheduled (active-pair) tracks.
    active_ids = [m["id"] for m in registry.metas() if m["active"]]
    last_touch = None
    total_done = total_weeks = 0
    for meta in registry.all_tracks():
        data = registry.load_track(meta["id"])
        weeks = (data or {}).get("weeks", [])
        total_weeks += len(weeks)
        for w in weeks:
            if w.get("status") == "completed":
                total_done += 1
            for k in ("started_at", "completed_at"):
                d = _d(w.get(k))
                if d and (last_touch is None or d > last_touch):
                    last_touch = d
    if total_weeks:
        idle = (today - last_touch).days if last_touch else None
        # sprint health = logged vs planned learning minutes so far this week
        # (day_blocks actuals for the active tracks' categories)
        try:
            import dayplan
            ws = dayplan.week_summary(today - timedelta(days=today.weekday()))
            planned = actual = 0
            for d_iso, cats in ws["days"].items():
                if d_iso > today.isoformat():
                    continue
                for cat in active_ids:
                    c = cats.get(cat)
                    if c:
                        planned += c["planned"]
                        actual += c["actual"]
        except Exception:
            planned = actual = 0
        if planned:
            ratio = actual / planned
            out["learning"] = {"status": _rung(on=ratio >= 0.7, at=ratio >= 0.4),
                               "detail": f"{actual / 60:.1f}/{planned / 60:.1f} h logged this week · {total_done}/{total_weeks} wks",
                               "metrics": {"done": total_done, "weeks": total_weeks,
                                           "week_actual_min": actual, "week_planned_min": planned}}
        else:
            out["learning"] = {"status": _rung(on=idle is not None and idle <= 7,
                                               at=idle is not None and idle <= 14),
                               "detail": (f"{total_done}/{total_weeks} wks · last activity {idle}d ago"
                                          if idle is not None else f"{total_done}/{total_weeks} wks · no activity logged"),
                               "metrics": {"done": total_done, "weeks": total_weeks, "idle_days": idle}}
    return out


def _triage(items, today):
    """Overdue, not-done rows worth a decision: milestones + ad-hoc events.
    Each row carries a suggested reschedule date."""
    today_iso = today.isoformat()
    suggested = (today + timedelta(days=14)).isoformat()
    out = []
    for i in items:
        if i["done"] or i["date"] >= today_iso:
            continue
        is_event = i["source"] == "timeline" and i["meta"].get("kind") == "event"
        if i["source"] == "milestone" or is_event:
            out.append({**i, "suggested": suggested})
    out.sort(key=lambda i: i["date"])
    return out


def board():
    today = date.today()
    items = []
    _collect(items, today)
    items.sort(key=lambda i: (i["date"], LANES.index(i["lane"]) if i["lane"] in LANES else 99))
    return {
        "items": items,
        "anchors": anchors.plan_anchors(),
        "lanes": LANES,
        "today": today.isoformat(),
        "health": _health(items, today),
        "triage": _triage(items, today),
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }
