"""Hour-by-hour day planner.

A day is generated from a template in schedule.yaml (weekday / saturday /
sunday / bridge_weekday) and each block's title + detail are filled from live
data: the daily job pull, overdue follow-ups, the current learning week and its
next unchecked deliverable, the next open profile-link item, the next cert step.
Categories that belong to a disabled module (agent.config.MODULE_DEFAULTS) are
skipped. Rows persist in day_blocks so ticks / actual minutes / drags survive reloads.
"""
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

import certs
import db
import health
import projects
import yamlio
import registry
from agent.config import load_settings, modules

# schedule.yaml is the user's own (gitignored) copy, written by Settings -> Day
# templates. Until it exists, the shipped schedule.example.yaml is read instead.
SCHEDULE_FILE = Path(os.environ.get("ASCENT_SCHEDULE") or Path(__file__).parent / "schedule.yaml")
SCHEDULE_EXAMPLE = Path(__file__).parent / "schedule.example.yaml"
_HEADER = (
    '# Today renders these as an ordered goal list, not a timetable.\n'
    "# `start` is only the sort key; `min` is the goal's size and still drives\n"
    '# week_summary() and the weekly hour budget. Real times are kept so the\n'
    '# hour-by-hour view can be restored later without a data migration.\n'
)

CATS = {
    "apps": {"label": "Applications", "color": "#3b82f6"},
    "controls": {"label": "Controls lab", "color": "#22d3ee"},
    "ml": {"label": "ML block", "color": "#8b5cf6"},
    "outreach": {"label": "Outreach", "color": "#f59e0b"},
    "clips": {"label": "Clips", "color": "#ec4899"},
    "portfolio": {"label": "Portfolio + links", "color": "#10b981"},
    "review": {"label": "Review", "color": "#94a3b8"},
    "break": {"label": "Break", "color": "#334155"},
    "bridge": {"label": "Bridge shift", "color": "#a3e635"},
    "gym": {"label": "Gym", "color": "#f97316"},
    "study": {"label": "Study", "color": "#14b8a6"},
    "social": {"label": "Social skills", "color": "#e879f9"},
    "project": {"label": "Project ship", "color": "#84cc16"},
    "cert": {"label": "Cert study", "color": "#eab308"},
}
# Categories owned by an optional module; every other category is always on.
MODULE_OF_CAT = {"clips": "clips", "gym": "health", "bridge": "side"}

# Weekday (0 = Monday) -> study topic. settings.yaml `study_plan` / `study_topics`
# override or extend these per user.
STUDY_PLAN = {0: "interview", 1: "plc_theory", 2: "interview", 3: "plc_theory", 4: "interview", 5: "plc_theory", 6: "interview"}
STUDY_TOPICS = {
    "interview": ("Interview prep", "Write + speak 1 STAR story (strongest project or past role) · 1 PLC technical Q "
                                    "(scan cycle, TON/TOF, interlocks, Modbus FC5/FC16) · 1 systems Q. Keep the stories in one doc."),
    "plc_theory": ("PLC theory", "IEC 61131-3 / Modbus / SoftMotion reading — no lab, pure reading + notes. Add 2 glossary terms."),
}
SOCIAL_COURSE_ROTATION = [  # settings.yaml `social_courses` replaces this list
    "Communication course of your choice — 1 lesson, 1 technique to try today",
    "Mock-interview video — watch 1, note 1 answer structure to reuse",
    "Networking guide — 1 principle, use it in today's reach-out",
]


def active_cats(settings=None):
    """CATS minus the categories whose module is switched off."""
    on = modules(settings if settings is not None else load_settings())
    return {k: v for k, v in CATS.items() if on.get(MODULE_OF_CAT.get(k, ""), True)}
_DEFAULT_SCHEDULE = {"wake": "07:00", "hard_stop": "19:15",
                     "templates": {"weekday": [], "saturday": [], "sunday": [], "bridge_weekday": [],
                                   "pre_sprint": []}}


def _hhmm(v):
    """Normalise a clock value. YAML 1.1 reads an unquoted 08:30 as the
    sexagesimal int 510, so ints are converted back to HH:MM."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return f"{v // 60:02d}:{v % 60:02d}"
    s = str(v).strip()
    if ":" not in s:
        return None
    h, m = s.split(":", 1)
    try:
        return f"{int(h):02d}:{int(m[:2]):02d}"
    except ValueError:
        return None


class _Dumper(yaml.SafeDumper):
    pass


def _repr_str(dumper, value):
    style = '"' if len(value) == 5 and value[2] == ":" else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _repr_str)


# mtime-keyed parse cache for the raw yaml — /api/day re-parsed schedule.yaml on
# every hit. Only the parse is cached; the merged dict below is rebuilt each call
# because save_schedule() mutates what load_schedule() hands back.
_SCHED_CACHE: tuple[float, dict] | None = None


def load_schedule():
    global _SCHED_CACHE
    src = SCHEDULE_FILE if SCHEDULE_FILE.exists() else SCHEDULE_EXAMPLE
    try:
        key = (src, src.stat().st_mtime)
    except OSError:
        return dict(_DEFAULT_SCHEDULE)
    if _SCHED_CACHE and _SCHED_CACHE[0] == key:
        data = _SCHED_CACHE[1]
    else:
        try:
            data = yamlio.load(src.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            data = {}
        _SCHED_CACHE = (key, data)
    out = {**_DEFAULT_SCHEDULE, **data}
    out["wake"] = _hhmm(out.get("wake")) or _DEFAULT_SCHEDULE["wake"]
    out["hard_stop"] = _hhmm(out.get("hard_stop")) or _DEFAULT_SCHEDULE["hard_stop"]
    templates = {}
    for name, blocks in {**_DEFAULT_SCHEDULE["templates"], **(data.get("templates") or {})}.items():
        templates[name] = [{**b, "start": _hhmm(b.get("start"))} for b in (blocks or []) if _hhmm(b.get("start"))]
    out["templates"] = templates
    return out


def save_schedule(data):
    cur = load_schedule()
    for k in ("wake", "hard_stop"):
        if _hhmm(data.get(k)):
            cur[k] = _hhmm(data[k])
    if isinstance(data.get("templates"), dict):
        for name, blocks in data["templates"].items():
            if isinstance(blocks, list):
                cur["templates"][name] = [
                    {"start": _hhmm(b.get("start")), "min": int(b.get("min") or 0),
                     "cat": b.get("cat") or "review", **({"title": b["title"]} if b.get("title") else {})}
                    for b in blocks if _hhmm(b.get("start")) and b.get("cat")]
    SCHEDULE_FILE.write_text(_HEADER + yaml.dump(cur, Dumper=_Dumper, default_flow_style=False,
                                                 sort_keys=False, allow_unicode=True), encoding="utf-8")
    return cur


def template_name(day, settings=None):
    settings = settings or load_settings()
    try:
        start = date.fromisoformat(str(settings.get("sprint_start"))[:10])
    except (TypeError, ValueError):
        start = None
    if start and day < start:
        return "pre_sprint" if day.weekday() < 5 else "sunday"
    if day.weekday() == 6:
        return "sunday"
    if day.weekday() == 5:
        return "saturday"
    return "bridge_weekday" if settings.get("bridge_mode") else "weekday"


def add_min(hhmm, minutes):
    h, m = (int(x) for x in hhmm.split(":"))
    t = (h * 60 + m + int(minutes)) % (24 * 60)
    return f"{t // 60:02d}:{t % 60:02d}"


def minutes_between(a, b):
    ah, am = (int(x) for x in a.split(":"))
    bh, bm = (int(x) for x in b.split(":"))
    return max((bh * 60 + bm) - (ah * 60 + am), 0)


# ── per-category fillers (each returns title, detail, deep_link, source_kind, source_id) ──

def _current_week(track):
    weeks = [w for w in track.get("weeks", [])
             if not (w.get("parked") or str(w.get("title", "")).lstrip().lower().startswith("[parked]"))]
    return (next((w for w in weeks if w.get("status") == "in_progress"), None)
            or next((w for w in weeks if w.get("status") != "completed"), None))


def _fill_track(tid, short, nth=0):
    """nth > 0 is the same track's 2nd/3rd block that day. It points at the next
    deliverable after the one the earlier block took, so two goals never repeat."""
    tr = registry.load_track(tid)
    if not tr:
        return (f"{short}: track missing", "", "#/tracks", "track", tid)
    wk = _current_week(tr)
    if not wk:
        return (f"{short}: all weeks complete", "Log a portfolio polish pass instead.", "#/tracks", "track", tid)
    done = set(wk.get("objectives_done") or [])
    todo = [d for d in (wk.get("deliverables") or []) if d not in done]
    nxt = todo[min(nth, len(todo) - 1)] if todo else None
    bits = []
    if wk.get("scene"):
        bits.append(f"Scene: {wk['scene']}")
    if nxt:
        bits.append(f"Next: {nxt}")
    where = wk.get("lab_path") or wk.get("sandbox_path")
    if where:
        bits.append(f"Lab: {where}")
    title = f"{short}: W{wk['id']} {wk.get('title', '')}".strip() + (f" (part {nth + 1})" if nth else "")
    return (title, " · ".join(bits), "#/tracks", "track_week", f"{tid}:{wk['id']}")


def _fill_apps(settings):
    n = int(settings.get("daily_apps") or 4)
    picks, run_date = [], None
    try:
        import jobruns
        run_date = jobruns.latest_date()
        run = jobruns.get_run(run_date) if run_date else None
        if run:
            in_pipe = {(a.get("company") or "").strip().lower() for a in db.get_all()}
            cands = [j for j in run.get("jobs", []) if (j.get("company") or "").strip().lower() not in in_pipe]
            picks = [f"{j.get('company', '?')} — {j.get('title', '')}".strip(" —") for j in cands[:n]]
    except Exception:
        pass
    try:
        import reminders
        overdue = [r for r in reminders.compute_reminders() if r["kind"] == "followup"]
    except Exception:
        overdue = []
    detail = f"Target {n} tailored apps from the {run_date or 'latest'} pull."
    if picks:
        detail += " Top: " + "; ".join(picks)
    if overdue:
        detail += f" · {len(overdue)} follow-up(s) overdue"
    return (f"Apply: {n} tailored applications", detail, "#/applications", "jobrun", run_date)


def _fill_outreach():
    today = date.today()
    stale = []
    for a in db.get_all():
        if a.get("status") not in ("applied", "phone_screen", "technical", "onsite"):
            continue
        lc = a.get("last_contacted")
        try:
            days = (today - date.fromisoformat(lc[:10])).days if lc else None
        except ValueError:
            days = None
        if days is None or days >= 5:
            stale.append(a.get("company") or "?")
    detail = (f"{len(stale)} app(s) need a touch: " + ", ".join(stale[:4]) + ("…" if len(stale) > 4 else "")
              if stale else "Pipeline current — send 3 LinkedIn notes to hiring managers / recruiters.")
    return ("Outreach + follow-ups", detail, "#/applications", "outreach", None)


def _fill_clips(entry, settings):
    """Two shapes share the clips category: the weekly batch session that produces
    a week of renders, and the short daily block that ships them. Split on length
    so the template stays one category."""
    s = db.side_summary()
    stats = f"streak {s['streak_days']}d · {s['posts_mtd']} posts MTD"
    if int(entry.get("min") or 0) >= 90:
        tool, url = settings.get("clips_tool") or "Clip tool", settings.get("clips_url") or ""
        return ("Clips: batch-produce next week's posts",
                f"{tool}{' → ' + url if url else ''} · ingest 1 source · review picks · render + caption 5-7 clips "
                f"so the daily block has a queue · {stats}", url, "clips", None)
    return ("Clips: post 2 + reply to 5",
            f"Post 2 already-rendered clips (TikTok + Shorts) · reply to 5 comments · "
            f"log it in Side or the streak stays 0 · {stats}", "#/side", "clips", None)


def _fill_portfolio():
    open_links = [l for l in db.links_all() if l.get("status") != "done"]
    open_links.sort(key=lambda l: l.get("due") or "9999")
    if not open_links:
        return ("Portfolio: polish", "All profile links done — update GitHub READMEs / portfolio demos.",
                "#/links", "links", None)
    l = open_links[0]
    item = next((c["text"] for c in l["checklist"] if not c.get("done")), None)
    detail = (f"Next: {item}" if item else "Paste the final URL to close it out.") + (
        f" · due {l['due']}" if l.get("due") else "")
    return (f"Portfolio: {l['label']}", detail, "#/links", "link", l["id"])


def _fill_gym(day):
    return (f"Gym: {health.GYM_SPLIT[day.weekday()]}", health.gym_detail(day), "#/health", "gym", None)


def _fill_study(day, settings=None):
    settings = settings or {}
    plan = {**STUDY_PLAN, **{int(k): v for k, v in (settings.get("study_plan") or {}).items()}}
    topics = {**STUDY_TOPICS, **{k: tuple(v) for k, v in (settings.get("study_topics") or {}).items()}}
    key = plan.get(day.weekday(), "interview")
    label, detail = topics.get(key) or STUDY_TOPICS["interview"]
    if day.weekday() == 5:  # Saturday also carries the ML weekly review (Sunday is off)
        detail += " · ML weekly review (20 min): check this week's SHIP GATE, log hours, pick next week's blocking task."
    return (f"Study: {label}", detail, "", "study", key)


def _fill_social(day, settings=None):
    rotation = (settings or {}).get("social_courses") or SOCIAL_COURSE_ROTATION
    course = rotation[day.toordinal() % len(rotation)]
    return ("Social: 1 reach-out + 1 recorded answer",
            f"Send 1 coffee-chat / informational-interview request to a real engineer (LinkedIn or alumni network) · "
            f"record yourself answering 1 interview question, watch it back, write down 1 fix · 20 min course: {course}",
            "", "social", None)


def _fill_project():
    core = [projects.decorate(r) for r in db.projects_all() if r.get("tier") == "core"]
    if not core:
        return ("Project: promote a core project", "Open Projects → Review all.", "#/projects", "project", None)
    open_ = [p for p in core if p["ship_done"] < 5]
    if open_:
        p = sorted(open_, key=lambda p: (-p["ship_done"], -p["story_filled"], p["name"]))[0]
        left = [label for key, label in projects.SHIP_ITEMS if not p["ship"][key]]
        return (f"Project: {p['name']} — {left[0]}", "Left: " + " · ".join(left),
                f"#/projects?open={p['id']}", "project", p["id"])
    p = sorted(core, key=lambda p: (p["story_filled"], p["name"]))[0]
    blank = next((projects.STORY_LABELS[f] for f in projects.STORY_FIELDS if not (p.get(f) or "").strip()), None)
    detail = f"{p['name']}: write '{blank}'" if blank else "Every story written — record a 30-second pitch."
    return ("Project: all core shipped — write stories", detail, f"#/projects?open={p['id']}", "project", p["id"])


def _fill_cert(day):
    c = certs.next_study_cert(db.certs_all(), day)
    if not c:
        return ("Cert: pick a cert & set an exam date", "Open Certifications → Review all.", "#/certs", "cert", None)
    step = next(s for s in c["steps"] if not s["done"])
    p = certs.pace(c, day)
    if p["state"] in ("on_pace", "behind"):
        detail = f"{p['days_left']} d to exam · {'on pace' if p['state'] == 'on_pace' else 'behind'} · {p['hours_left']} h left"
    elif p["state"] == "past":
        detail = "Exam date passed — rebook or update it"
    else:
        detail = "No exam date — set one on the cert"
    return (f"Cert: {c['title']} — {step['text']}", detail, f"#/certs?open={c['id']}", "cert", c["id"])


def _fill(cat, entry, settings):
    day = date.fromisoformat(entry["_date"]) if entry.get("_date") else date.today()
    nth = int(entry.get("_nth") or 0)
    if cat == "gym":
        return _fill_gym(day)
    if cat == "study":
        return _fill_study(day, settings)
    if cat == "social":
        return _fill_social(day, settings)
    if cat == "apps":
        return _fill_apps(settings)
    if cat == "controls":
        return _fill_track("controls", "Controls", nth)
    if cat == "ml":
        return _fill_track("ml", "ML", nth)
    if cat == "outreach":
        return _fill_outreach()
    if cat == "clips":
        return _fill_clips(entry, settings)
    if cat == "portfolio":
        return _fill_portfolio()
    if cat == "project":
        return _fill_project()
    if cat == "cert":
        return _fill_cert(day)
    if cat == "review":
        return ("Review: log actuals, tick blocks, generate tomorrow",
                f"Update apps sent{' + clips posted' if modules(settings)['clips'] else ''}, "
                "then Regenerate tomorrow on Today.", "#/today", "review", None)
    if cat == "bridge":
        return (entry.get("title") or "Bridge shift", "Agency contract / part-time shift.", "#/side", "bridge", None)
    return (entry.get("title") or CATS.get(cat, {}).get("label", cat), "", "", cat, None)


# ── public API ────────────────────────────────────────────────────────────────

def generate(day=None, template=None, force=False):
    day = day or date.today()
    iso = day.isoformat()
    existing = db.day_blocks_for(iso)
    if existing and not force:
        return existing
    settings = load_settings()
    sched = load_schedule()
    name = template or template_name(day, settings)
    cats = active_cats(settings)
    entries = [e for e in (sched["templates"].get(name) or []) if (e.get("cat") or "review") in cats]
    if existing:
        db.day_blocks_clear(iso, keep_done=True)
        kept = {(b["start"], b["cat"]) for b in db.day_blocks_for(iso)}
    else:
        kept = set()
    seen = {}
    for pos, e in enumerate(entries):
        start = str(e.get("start"))
        cat = e.get("cat") or "review"
        nth = seen[cat] = seen.get(cat, -1) + 1
        if (start, cat) in kept:
            continue
        title, detail, link, skind, sid = _fill(cat, {**e, "_date": iso, "_nth": nth}, settings)
        db.day_block_create({
            "date": iso, "start": start, "end": add_min(start, e.get("min") or 30), "cat": cat,
            "title": title, "detail": detail, "deep_link": link,
            "source_kind": skind, "source_id": sid, "pos": pos,
        })
    return db.day_blocks_for(iso)


def day_payload(day=None):
    day = day or date.today()
    cats = active_cats()
    blocks = [b for b in generate(day) if b["cat"] in cats or b["cat"] not in CATS]
    sched = load_schedule()
    planned = sum(minutes_between(b["start"], b["end"]) for b in blocks if b["cat"] != "break")
    actual = sum(b.get("actual_min") or 0 for b in blocks)
    return {"date": day.isoformat(), "template": template_name(day), "blocks": blocks,
            "cats": cats, "wake": sched["wake"], "hard_stop": sched["hard_stop"],
            "planned_min": planned, "actual_min": actual,
            "done": sum(1 for b in blocks if b["status"] == "done"),
            "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat()}


def week_summary(start=None):
    """Planned vs actual minutes per category per day for the 7 days from `start`
    (defaults to this week's Monday). Days without rows are simply absent."""
    start = start or (date.today() - timedelta(days=date.today().weekday()))
    end = start + timedelta(days=6)
    rows = db.day_blocks_range(start.isoformat(), end.isoformat())
    cats = active_cats()
    days, totals = {}, {}
    for b in rows:
        if b["cat"] == "break" or (b["cat"] in CATS and b["cat"] not in cats):
            continue
        d = days.setdefault(b["date"], {})
        c = d.setdefault(b["cat"], {"planned": 0, "actual": 0, "done": 0, "blocks": 0})
        c["planned"] += minutes_between(b["start"], b["end"])
        c["actual"] += b.get("actual_min") or 0
        c["done"] += 1 if b["status"] == "done" else 0
        c["blocks"] += 1
    for d in days.values():
        for cat, c in d.items():
            t = totals.setdefault(cat, {"planned": 0, "actual": 0, "done": 0, "blocks": 0})
            for k in t:
                t[k] += c[k]
    return {"start": start.isoformat(), "end": end.isoformat(), "days": days, "totals": totals, "cats": cats}


def blocks_starting_within(minutes=5, now=None):
    """Today's planned blocks whose start is within [now, now+minutes] — for
    the toast notifier."""
    now = now or datetime.now()
    lo = now.strftime("%H:%M")
    hi = (now + timedelta(minutes=minutes)).strftime("%H:%M")
    return [b for b in db.day_blocks_for(now.date().isoformat())
            if b["status"] == "planned" and lo <= b["start"] <= hi]
