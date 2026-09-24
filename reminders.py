"""Reminder computation — single source of truth for both the in-app
notification center and the Windows toast notifier. Pure functions over career.db.
"""
from datetime import date, timedelta

import db

_CLOSED = {"offer", "rejected", "archived", "ghosted"}
FOLLOWUP_STALE_DAYS = 7


def _apps_per_week_target():
    try:
        from agent.config import load_settings
        return int(load_settings().get("weekly_target") or 20)
    except Exception:
        return 20


def _d(iso):
    if not iso:
        return None
    try:
        return date.fromisoformat(iso[:10])
    except ValueError:
        return None


def compute_reminders(today=None):
    today = today or date.today()
    out = []
    apps = db.get_all()

    for a in apps:
        if a.get("status") in _CLOSED:
            continue
        fu = _d(a.get("follow_up_date"))
        if fu and fu <= today:
            late = (today - fu).days
            out.append({
                "kind": "followup",
                "title": f"Follow up: {a['company']}",
                "body": f"{a['role']} — follow-up was {'due today' if late == 0 else f'{late}d ago'}.",
                "due": fu.isoformat(),
                "ref_type": "application", "ref_id": a["id"],
            })

    for a in apps:
        if a.get("status") not in ("applied", "phone_screen", "technical", "onsite"):
            continue
        if a.get("follow_up_date"):
            continue
        applied = _d(a.get("applied_date"))
        if applied and (today - applied).days >= FOLLOWUP_STALE_DAYS:
            out.append({
                # distinct kind: upsert keys it by application (not due date),
                # so dismissing the nag silences it instead of it reappearing daily
                "kind": "followup_missing",
                "title": f"No follow-up set: {a['company']}",
                "body": f"{a['role']} — applied {(today - applied).days}d ago, none scheduled.",
                "due": today.isoformat(),
                "ref_type": "application", "ref_id": a["id"],
            })

    horizon = today + timedelta(days=7)
    for e in db.timeline_all():
        if e.get("done"):
            continue
        ed = _d(e.get("date"))
        if ed and today <= ed <= horizon:
            days = (ed - today).days
            when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days}d"
            out.append({
                "kind": "deadline",
                "title": f"{str(e.get('kind', 'event')).title()}: {e['label']}",
                "body": f"Due {when} ({ed.isoformat()}).",
                "due": ed.isoformat(),
                "ref_type": "timeline", "ref_id": e["id"],
            })

    if today.weekday() == 0:
        week_ago = today - timedelta(days=7)
        recent = sum(1 for a in apps if (_d(a.get("applied_date")) or date.min) >= week_ago)
        target = _apps_per_week_target()
        if recent < target:
            out.append({
                "kind": "cadence",
                "title": "Application cadence behind",
                "body": f"{recent}/{target} applications in the last 7 days.",
                "due": today.isoformat(),
                "ref_type": "cadence", "ref_id": f"week-{today.isoformat()}",
            })

    return out


def sync_reminders(today=None):
    for r in compute_reminders(today):
        db.reminder_upsert(r)
    return db.reminders_open()


def digest(today=None):
    today = today or date.today()
    items = compute_reminders(today)
    if not items:
        return "Ascent: all clear — no follow-ups or deadlines today."
    order = {"deadline": 0, "followup": 1, "followup_missing": 2, "cadence": 3}
    items.sort(key=lambda r: order.get(r["kind"], 9))
    lines = [f"• {r['title']}" for r in items[:6]]
    extra = len(items) - len(lines)
    if extra > 0:
        lines.append(f"• +{extra} more")
    return "Ascent — today:\n" + "\n".join(lines)


if __name__ == "__main__":
    import sys
    if "--sync" in sys.argv:
        print(f"synced; {len(sync_reminders())} open reminders")
    else:
        for r in compute_reminders():
            print(f"[{r['kind']}] {r['title']} — {r['body']}")
        print("\n--- digest ---\n" + digest())
