#!/usr/bin/env python3
"""
Ascent API — Flask routes over career.db (served by app.py on :5001).
Run standalone:  python tracker.py   (http://localhost:5000)
Debug: FLASK_DEBUG=1 python tracker.py
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, send_file, stream_with_context

# Load .env before the local imports: db / agent.config / data resolve their
# ASCENT_DB / ASCENT_SETTINGS / TRACKER_DATA paths at import time.
load_dotenv(Path(__file__).parent / ".env")

import anchors  # noqa: E402
import db  # noqa: E402
import focus  # noqa: E402
import projects  # noqa: E402
import roadmaps  # noqa: E402
import yamlio  # noqa: E402

# data.yaml only holds resume_templates variants now (read by agent.resume_tailor)
from data import DATA_FILE as _DATA_PATH  # noqa: E402


def _target_date() -> date:
    """Working deadline = next cert exam, else projected learning-program end
    (single source of truth in anchors.py). Keeps the morning brief in sync
    with the Timeline, Focus and Dashboard countdowns."""
    return anchors.deadline()

def _first_name() -> str:
    from agent.profile import first_name
    return first_name()


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = Flask(__name__)

# Gzip compression for responses
try:
    from flask_compress import Compress
    Compress(app)
except ImportError:
    pass  # optional dependency

# ── agent routes ───────────────────────────────────────────────────────────────

@app.route("/api/agent/ask", methods=["POST"])
def api_agent_ask():
    body = request.json or {}
    query = body.get("query", "").strip()
    if not query:
        return jsonify({"ok": False, "error": "query required"}), 400

    try:
        context = _build_linda_context()
    except Exception:
        logging.exception("linda context build failed; proceeding without it")
        context = None

    def generate():
        try:
            from agent.agent import run_agent
            for event in run_agent(query, context):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'answer', 'text': f'Agent error: {exc}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/agent/history", methods=["GET"])
def api_agent_history_get():
    """Return recent Linda chat history."""
    from agent.history import load_history
    limit = min(int(request.args.get("limit", 20)), 50)
    return jsonify({"entries": load_history(limit)})


@app.route("/api/agent/history", methods=["POST"])
def api_agent_history_post():
    """Append a Linda chat entry to history."""
    from agent.history import append_entry
    body = request.json or {}
    query = (body.get("query") or "").strip()
    answer = (body.get("answer") or "").strip()
    tools = body.get("tools_used") or []
    if not query or not answer:
        return jsonify({"ok": False, "error": "query and answer required"}), 400
    if not isinstance(tools, list):
        tools = []
    append_entry(query, answer, tools)
    return jsonify({"ok": True})


@app.route("/api/agent/history", methods=["DELETE"])
def api_agent_history_delete():
    """Clear all Linda chat history."""
    from agent.history import clear_history
    clear_history()
    return jsonify({"ok": True})


# ── notes / journal routes ──────────────────────────────────────────────────────

@app.route("/api/notes", methods=["GET"])
def api_notes_get():
    return jsonify({"entries": db.notes_all()})


@app.route("/api/notes", methods=["POST"])
def api_notes_post():
    """Add a new journal entry. Body: {"text": "..."}"""
    body = request.json or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text required"}), 400
    return jsonify({"ok": True, "note": db.note_create(text)})


@app.route("/api/notes/<note_id>", methods=["DELETE"])
def api_notes_delete(note_id):
    if not db.note_delete(note_id):
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/notes/<note_id>", methods=["PUT"])
def api_notes_update(note_id):
    body = request.json or {}
    text = body.get("text")
    if text is not None:
        text = text.strip()
        if not text:
            return jsonify({"ok": False, "error": "text required"}), 400
    rec = db.note_update(note_id, text=text, pinned=body.get("pinned"))
    if not rec:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True, "note": rec})


# ── applications (SQLite) ─────────────────────────────────────────────────────

@app.route("/api/applications", methods=["GET"])
def api_applications_get():
    status = request.args.get("status")
    company = request.args.get("company")
    return jsonify(db.get_all(status=status, company=company))


@app.route("/api/applications", methods=["POST"])
def api_applications_post():
    body = request.json or {}
    record = db.create(body)
    return jsonify(record), 201


@app.route("/api/applications/<app_id>", methods=["PUT"])
def api_applications_put(app_id):
    body = request.json or {}
    record = db.update(app_id, body)
    if not record:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(record)


@app.route("/api/applications/<app_id>", methods=["DELETE"])
def api_applications_delete(app_id):
    db.soft_delete(app_id)
    return jsonify({"ok": True})


@app.route("/api/applications/stats", methods=["GET"])
def api_applications_stats():
    return jsonify(db.get_stats())


@app.route("/api/applications/funnel", methods=["GET"])
def api_applications_funnel():
    """Stage-to-stage conversion rates across active applications."""
    return jsonify(db.get_funnel())


@app.route("/api/applications/cadence", methods=["GET"])
def api_applications_cadence():
    """Weekly apps vs target by bucket + the overdue-first follow-up queue."""
    return jsonify(db.get_cadence())


@app.route("/api/applications/duplicate", methods=["GET"])
def api_applications_duplicate():
    """Pre-add dedup check by url, else (company, role). Returns the match or null."""
    dup = db.find_app_duplicate(
        company=request.args.get("company"),
        role=request.args.get("role"),
        url=request.args.get("url"))
    return jsonify({"duplicate": bool(dup), "existing": dup})


# ── goals (SQLite — career.db is the single source of truth) ───────────────────

@app.route("/api/goals/milestones", methods=["GET"])
def api_goals_milestones_get():
    return jsonify(db.milestones_all())


@app.route("/api/goals/milestones", methods=["POST"])
def api_goals_milestones_post():
    body = request.json or {}
    if not (body.get("text") or "").strip():
        return jsonify({"ok": False, "error": "text required"}), 400
    return jsonify(db.milestone_create(body)), 201


@app.route("/api/calendar.ics", methods=["GET"])
def api_calendar_ics():
    """Export follow-ups, milestone due-dates and timeline events as an .ics."""
    def esc(s):
        return (str(s or "").replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Ascent//Career OS//EN", "CALSCALE:GREGORIAN"]

    def event(uid, iso_date, summary):
        d = (iso_date or "")[:10].replace("-", "")
        if len(d) != 8:
            return
        lines.extend(["BEGIN:VEVENT", f"UID:{esc(uid)}@ascent",
                      f"DTSTART;VALUE=DATE:{d}", f"SUMMARY:{esc(summary)}", "END:VEVENT"])

    for a in db.get_all():
        if a.get("follow_up_date") and a.get("status") not in ("offer", "rejected"):
            event(f"fu-{a['id']}", a["follow_up_date"], f"Follow up: {a['company']} ({a['role']})")
    for m in db.milestones_all():
        if m.get("due") and not m.get("done"):
            event(f"ms-{m['id']}", m["due"], f"Milestone: {m['text']}")
    for e in db.timeline_all():
        if e.get("date") and not e.get("done"):
            event(f"tl-{e['id']}", e["date"], e["label"])

    lines.append("END:VCALENDAR")
    body = "\r\n".join(lines) + "\r\n"
    return Response(body, mimetype="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=ascent.ics"})


@app.route("/api/goals/milestones/<mid>", methods=["PUT"])
def api_goals_milestone_put(mid):
    """No body → toggle done; body → update allowed fields."""
    body = request.json or {}
    rec = db.milestone_update(mid, body) if body else db.milestone_toggle(mid)
    if not rec:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(rec)


@app.route("/api/goals/milestones/<mid>", methods=["DELETE"])
def api_goals_milestone_delete(mid):
    if not db.milestone_delete(mid):
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/goals/weekly", methods=["GET"])
def api_goals_weekly_get():
    return jsonify(db.weekly_all(week=request.args.get("week")))


@app.route("/api/goals/weekly", methods=["POST"])
def api_goals_weekly_post():
    body = request.json or {}
    text = (body.get("text") or "").strip()
    week = (body.get("week") or "").strip()
    if not text or not week:
        return jsonify({"ok": False, "error": "week and text required"}), 400
    return jsonify(db.weekly_create({"week": week, "text": text})), 201


@app.route("/api/goals/weekly/<wid>", methods=["PUT"])
def api_goals_weekly_put(wid):
    rec = db.weekly_toggle(wid)
    if not rec:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(rec)


@app.route("/api/goals/weekly/<wid>", methods=["DELETE"])
def api_goals_weekly_delete(wid):
    if not db.weekly_delete(wid):
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/skills", methods=["GET"])
def api_skills_get():
    return jsonify(db.skills_all())


@app.route("/api/skills", methods=["POST"])
def api_skills_post():
    body = request.json or {}
    if not (body.get("skill") or "").strip():
        return jsonify({"ok": False, "error": "skill required"}), 400
    return jsonify(db.skill_create(body)), 201


@app.route("/api/skills/<sid>", methods=["PUT"])
def api_skills_update(sid):
    body = request.json or {}
    if "hours" in body and len(body) == 1:
        rec = db.skill_log_hours(sid, body.get("hours", 1))
    else:
        rec = db.skill_update(sid, body)
    if not rec:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(rec)


@app.route("/api/skills/<sid>", methods=["DELETE"])
def api_skills_delete(sid):
    if not db.skill_delete(sid):
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/skills/gap-analysis", methods=["GET"])
def api_skills_gap_analysis():
    """Match tracked skill proficiencies against a target role profile."""
    pid = request.args.get("profile")
    result = roadmaps.gap_analysis(pid) if pid else None
    if result is None:
        return jsonify({"ok": False, "error": "profile required or not found"}), 404
    return jsonify(result)


# ── roadmaps + job profiles (data/roadmaps, data/job_profiles) ─────────────────
@app.route("/api/roadmaps", methods=["GET"])
def api_roadmaps_get():
    return jsonify(roadmaps.all_roadmaps())


@app.route("/api/roadmaps/<rid>", methods=["GET"])
def api_roadmap_get(rid):
    data = roadmaps.load_roadmap(rid)
    if data is None:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(data)


@app.route("/api/roadmaps/<rid>/progress/<node_id>", methods=["PUT"])
def api_roadmap_progress(rid, node_id):
    body = request.json or {}
    state = body.get("state")
    if state not in roadmaps.VALID_STATES:
        return jsonify({"ok": False, "error": "invalid state"}), 400
    if roadmaps.load_roadmap(rid) is None:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(db.roadmap_set_node(rid, node_id, state, body.get("notes")))


@app.route("/api/jobprofiles", methods=["GET"])
def api_jobprofiles_get():
    return jsonify(roadmaps.all_profiles())


@app.route("/api/focus", methods=["GET"])
def api_focus_get():
    """Ranked next actions toward a target role by the plan deadline."""
    result = focus.compute(request.args.get("profile"))
    if result is None:
        return jsonify({"ok": False, "error": "profile required or not found"}), 404
    return jsonify(result)


# ── certifications (SQLite) ────────────────────────────────────────────────────

@app.route("/api/certifications", methods=["GET"])
def api_certifications_get():
    """List certifications. Optional ?track=&status= filters."""
    return jsonify(db.certs_all(track=request.args.get("track"), status=request.args.get("status")))


@app.route("/api/certifications/summary", methods=["GET"])
def api_certifications_summary():
    import certs
    from agent.config import load_settings
    s = load_settings()
    rows = db.certs_all()
    today = date.today()
    return jsonify({
        "budget": certs.budget(rows, s.get("runway_end"), s.get("cert_budget")),
        "pace": {r["id"]: certs.pace(r, today) for r in rows if r.get("status") == certs.ACTIVE},
    })


@app.route("/api/certifications", methods=["POST"])
def api_certifications_post():
    body = request.json or {}
    if not (body.get("title") or "").strip():
        return jsonify({"ok": False, "error": "title required"}), 400
    return jsonify(db.cert_create(body)), 201


@app.route("/api/certifications/<cert_id>", methods=["PUT"])
def api_certifications_put(cert_id):
    rec = db.cert_update(cert_id, request.json or {})
    if not rec:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(rec)


@app.route("/api/certifications/<cert_id>", methods=["DELETE"])
def api_certifications_delete(cert_id):
    if not db.cert_delete(cert_id):
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


# ── timeline events (SQLite) ───────────────────────────────────────────────────

@app.route("/api/timeline", methods=["GET"])
def api_timeline_get():
    """List timeline events sorted by date asc. Optional ?track=&phase= filters."""
    return jsonify(db.timeline_all(track=request.args.get("track"), phase=request.args.get("phase")))


@app.route("/api/timeline", methods=["POST"])
def api_timeline_post():
    body = request.json or {}
    label = (body.get("label") or "").strip()
    event_date = (body.get("date") or "").strip()
    if not label:
        return jsonify({"ok": False, "error": "label required"}), 400
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_date):
        return jsonify({"ok": False, "error": "date must be YYYY-MM-DD"}), 400
    return jsonify(db.timeline_create(body)), 201


@app.route("/api/timeline/<event_id>", methods=["PUT"])
def api_timeline_put(event_id):
    rec = db.timeline_update(event_id, request.json or {})
    if not rec:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(rec)


@app.route("/api/timeline/<event_id>", methods=["DELETE"])
def api_timeline_delete(event_id):
    if not db.timeline_delete(event_id):
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/timeline/board", methods=["GET"])
def api_timeline_board():
    """Unified Gantt payload: aggregated items + anchors + health + triage."""
    import timeline_board
    return jsonify(timeline_board.board())


@app.route("/api/anchors", methods=["GET"])
def api_anchors():
    """Headline plan dates (next exam / program end / primary goal) — one source
    of truth so every section's countdowns agree."""
    return jsonify({**anchors.plan_anchors(), "name": _first_name()})


# ── morning brief ──────────────────────────────────────────────────────────────

@app.route("/api/brief", methods=["GET"])
def api_brief():
    stats = db.get_stats()

    # Target date and days remaining
    target_date = _target_date()
    today = date.today()
    days_to_deadline = (target_date - today).days

    # Top skill gaps (not complete, by priority)
    skill_gaps = db.skills_all()
    top_gaps = []
    for gap in skill_gaps:
        if not gap.get("complete", False):
            pct = round(
                (gap.get("hours_logged", 0) / gap.get("target_hours", 1) * 100)
                if gap.get("target_hours") else 0,
                1
            )
            top_gaps.append({
                "skill": gap.get("skill"),
                "hours_logged": gap.get("hours_logged", 0),
                "target_hours": gap.get("target_hours", 0),
                "pct": pct
            })

    top_gaps.sort(key=lambda x: x["pct"])
    top_gaps = top_gaps[:2]

    # Message
    if stats["overdue_count"] > 0:
        message = f"{stats['overdue_count']} follow-ups overdue"
    else:
        message = "On track"

    return jsonify({
        "greeting": f"Good morning, {_first_name()}." if _first_name() else "Good morning.",
        "date": today.strftime("%b %d, %Y"),
        "days_to_deadline": days_to_deadline,
        "target_date": target_date.isoformat(),
        "stats": stats,
        "top_skill_gaps": top_gaps,
        "message": message
    })


# ── linda context ──────────────────────────────────────────────────────────────

def _build_linda_context():
    stats = db.get_stats()
    days_to_deadline = (_target_date() - date.today()).days
    return {
        "applications": db.get_all(),
        "stats": stats,
        "goals": {
            "milestones": db.milestones_all(),
            "skill_gaps": db.skills_all(),
        },
        "days_to_deadline": days_to_deadline,
    }


@app.route("/api/linda/context", methods=["GET"])
def api_linda_context():
    return jsonify(_build_linda_context())


# ── reminders / notifications ───────────────────────────────────────────────────

@app.route("/api/reminders", methods=["GET"])
def api_reminders_get():
    import reminders as rmod
    rmod.sync_reminders()
    return jsonify(db.reminders_open())


@app.route("/api/reminders/sync", methods=["POST"])
def api_reminders_sync():
    import reminders as rmod
    return jsonify(rmod.sync_reminders())


@app.route("/api/reminders/<rid>", methods=["PUT"])
def api_reminders_put(rid):
    body = request.json or {}
    rec = db.reminder_mark(rid, read=body.get("read"), dismissed=body.get("dismissed"))
    if not rec:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(rec)


# ── ai agents (stub routes) ────────────────────────────────────────────────────

@app.route("/api/jobs/scan", methods=["POST"])
def api_jobs_scan():
    try:
        from agent.job_search import scan_jobs
        return jsonify({"ok": True, "jobs": scan_jobs()})
    except Exception as exc:
        logging.exception("job scan failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── Cowork daily job pull (job_runs/) ────────────────────────────────────────────

@app.route("/api/jobs/runs", methods=["GET"])
def api_jobs_runs():
    import jobruns
    return jsonify({"runs": jobruns.list_runs(), "latest": jobruns.latest_date()})


@app.route("/api/jobs/runs/<date>", methods=["GET"])
def api_jobs_run(date):
    import jobruns
    run = jobruns.get_run(date)
    if not run:
        return jsonify({"ok": False, "error": "run not found"}), 404
    return jsonify(run)


@app.route("/api/jobs/file/<date>/<slug>/<which>", methods=["GET"])
def api_jobs_file(date, slug, which):
    import jobruns
    path = jobruns.job_file(date, slug, which)
    if not path:
        return jsonify({"ok": False, "error": "file not found"}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


# ── live news (Google News RSS) ──────────────────────────────────────────────────

@app.route("/api/news", methods=["GET"])
def api_news():
    import news
    topics = (request.args.get("topics") or "robotics,ai,az").split(",")
    return jsonify(news.get_news([t.strip() for t in topics if t.strip()]))


@app.route("/api/glossary", methods=["GET"])
def api_glossary():
    import glossary
    return jsonify({"terms": glossary.as_list()})


@app.route("/api/agent/tailor", methods=["POST"])
def api_agent_tailor():
    body = request.json or {}
    jd = (body.get("job_description") or "").strip()
    variant = body.get("variant") or ""
    if not jd:
        return jsonify({"ok": False, "error": "job_description required"}), 400
    try:
        from agent.resume_tailor import tailor_resume
        return jsonify(tailor_resume(jd, variant))
    except Exception as exc:
        logging.exception("tailor failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/agent/cover-letter", methods=["POST"])
def api_agent_cover_letter():
    body = request.json or {}
    company = (body.get("company") or "").strip()
    role = (body.get("role") or "").strip()
    variant = body.get("variant") or ""
    if not company or not role:
        return jsonify({"ok": False, "error": "company and role required"}), 400
    try:
        from agent.resume_tailor import generate_cover_letter
        return jsonify(generate_cover_letter(company, role, variant))
    except Exception as exc:
        logging.exception("cover letter failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/resume/variants", methods=["GET"])
def api_resume_variants():
    """Resume angle presets (resume_templates in data.yaml) for the Studio picker."""
    import yaml
    try:
        data = yamlio.load(Path(_DATA_PATH).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    return jsonify([
        {"id": v.get("id"), "name": v.get("name") or v.get("id"),
         "target_roles": v.get("target_roles") or [],
         "skills_emphasis": v.get("skills_emphasis") or []}
        for v in data.get("resume_templates", []) if v.get("id")
    ])


@app.route("/api/resume/download", methods=["POST"])
def api_resume_download():
    body = request.json or {}
    token = body.get("doc_token")
    if not token:
        return jsonify({"ok": False, "error": "doc_token required"}), 400
    try:
        from agent.resume_tailor import render_docx
        path = render_docx(token)
    except KeyError:
        return jsonify({"ok": False, "error": "expired or unknown doc_token"}), 404
    except Exception as exc:
        logging.exception("docx render failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
    return send_file(path, as_attachment=True, download_name=path.name)


# ── settings (app + LLM) ───────────────────────────────────────────────────────

def _free_ram_gib():
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return round(m.ullAvailPhys / 1024**3, 1)
    except Exception:
        return None


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    from agent.config import CURATED_MODELS, FALLBACK_MODEL, load_settings
    s = load_settings()
    ollama_info = {"reachable": False, "models": [], "error": None}
    try:
        import ollama
        from agent.config import PROBE_TIMEOUT
        data = ollama.Client(host=s["ollama_host"], timeout=PROBE_TIMEOUT).list()
        ollama_info["reachable"] = True
        ollama_info["models"] = sorted(
            (m.get("model") or m.get("name") or "") for m in data.get("models", [])
        )
    except Exception as exc:
        ollama_info["error"] = str(exc)
    return jsonify({
        "settings": s,
        "ollama": ollama_info,
        "free_ram_gib": _free_ram_gib(),
        "fallback_model": FALLBACK_MODEL,
        "curated": CURATED_MODELS,
        "app": {
            "ascent_port": 5001,
            "data_yaml": str(_DATA_PATH),
            "output_dir": str(Path(__file__).parent / "output"),
        },
    })


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    from agent.config import save_settings
    body = request.json or {}
    return jsonify({"ok": True, "settings": save_settings(body)})


@app.route("/api/settings/test", methods=["POST"])
def api_settings_test():
    body = request.json or {}
    from agent.config import load_settings
    model = (body.get("model") or load_settings()["model"]).strip()
    try:
        import time
        t0 = time.time()
        from agent.config import make_client
        make_client(timeout=60).chat(
            model=model,
            messages=[{"role": "user", "content": "Reply with the word: ok"}],
            options={"num_predict": 5},
        )
        return jsonify({"ok": True, "model": model,
                        "latency_ms": round((time.time() - t0) * 1000)})
    except Exception as exc:
        return jsonify({"ok": False, "model": model, "error": str(exc)})


@app.route("/api/settings/pull", methods=["POST"])
def api_settings_pull():
    body = request.json or {}
    model = (body.get("model") or "").strip()
    if not model:
        return jsonify({"ok": False, "error": "model required"}), 400

    def generate():
        try:
            from agent.config import make_client
            # long read timeout: pulls stream steady progress chunks for minutes
            for ev in make_client(timeout=600).pull(model, stream=True):
                ev = dict(ev) if not isinstance(ev, dict) else ev
                status = ev.get("status", "")
                total = ev.get("total") or 0
                completed = ev.get("completed") or 0
                pct = round(100 * completed / total) if total else None
                yield f"data: {json.dumps({'status': status, 'pct': pct})}\n\n"
            yield f"data: {json.dumps({'status': 'success', 'pct': 100, 'done': True})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'status': 'error', 'error': str(exc), 'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/interview/prep", methods=["POST"])
def api_interview_prep():
    body = request.json or {}
    company = (body.get("company") or "").strip()
    role = (body.get("role") or "").strip()
    if not company or not role:
        return jsonify({"ok": False, "error": "company and role required"}), 400
    try:
        from agent.interview_prep import generate_prep
        return jsonify(generate_prep(company, role))
    except Exception as exc:
        logging.exception("interview prep failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/intel/<company>", methods=["POST"])
def api_intel(company):
    try:
        from agent.company_intel import research_company
        return jsonify(research_company(company.strip()))
    except Exception as exc:
        logging.exception("company intel failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/offer/analyze", methods=["POST"])
def api_offer_analyze():
    body = request.json or {}
    offer = body.get("offer") if isinstance(body.get("offer"), dict) else body
    try:
        offer = {k: (float(v) if str(v).replace(".", "", 1).isdigit() else v)
                 for k, v in (offer or {}).items()}
        from agent.offer_analyzer import analyze_offer
        return jsonify(analyze_offer(offer))
    except Exception as exc:
        logging.exception("offer analyze failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ── learning tracks (data-driven registry: tracks/<id>.yaml) ────────────────────

import registry

_VALID_STATUS = ("not_started", "in_progress", "completed")


@app.route("/api/tracks", methods=["GET"])
def api_tracks_list():
    """Summary of every track in tracks/ (id, title, category, schedule, counts, %)."""
    return jsonify(registry.all_tracks())


@app.route("/api/tracks/<track>", methods=["GET"])
def api_track_get(track):
    """Static track yaml merged with live per-week DB progress."""
    data = registry.load_track(track)
    if data is None:
        return jsonify({"ok": False, "error": "unknown track"}), 404
    return jsonify(data)


@app.route("/api/tracks/<track>/week/<int:week_id>", methods=["PUT"])
def api_track_week_put(track, week_id):
    if not registry.exists(track):
        return jsonify({"ok": False, "error": "unknown track"}), 404
    body = request.json or {}
    status = body.get("status")
    if status not in _VALID_STATUS:
        return jsonify({"ok": False, "error": "invalid status"}), 400
    db.track_set_week(track, week_id, status, notes=body.get("notes"))
    return jsonify({"ok": True})


@app.route("/api/tracks/<track>/week/<int:week_id>/detail", methods=["PUT"])
@app.route("/api/<track>/week/<int:week_id>/detail", methods=["PUT"])
def api_track_detail(track, week_id):
    """Persist per-week checked objectives + can_explain + logged hours."""
    if not registry.exists(track):
        return jsonify({"ok": False, "error": "unknown track"}), 404
    body = request.json or {}
    rec = db.track_detail_set(
        track, week_id,
        objectives_done=body.get("objectives_done"),
        can_explain_done=body.get("can_explain_done"),
        hours=body.get("hours"),
    )
    return jsonify({"ok": True, **rec})


# ── day plan (hour-by-hour) ────────────────────────────────────────────────────

def _parse_day(s):
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return date.today()


@app.route("/api/day", methods=["GET"])
def api_day_get():
    import dayplan
    return jsonify(dayplan.day_payload(_parse_day(request.args.get("date"))))


@app.route("/api/day/generate", methods=["POST"])
def api_day_generate():
    import dayplan
    body = request.json or {}
    day = _parse_day(body.get("date"))
    dayplan.generate(day, template=body.get("template"), force=bool(body.get("force", True)))
    return jsonify(dayplan.day_payload(day))


@app.route("/api/day/week", methods=["GET"])
def api_day_week():
    import dayplan
    start = request.args.get("start")
    return jsonify(dayplan.week_summary(_parse_day(start) if start else None))


@app.route("/api/day/<bid>", methods=["PUT"])
def api_day_put(bid):
    body = request.json or {}
    if body.get("status") not in (None, "planned", "done", "skipped"):
        return jsonify({"ok": False, "error": "invalid status"}), 400
    row = db.day_block_update(bid, body)
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(row)


@app.route("/api/day/<bid>/shift", methods=["POST"])
def api_day_shift(bid):
    """Move a block by ±minutes (keeps its length)."""
    import dayplan
    row = db.get_row("day_blocks", bid)
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    delta = int((request.json or {}).get("min") or 0)
    return jsonify(db.day_block_update(bid, {"start": dayplan.add_min(row["start"], delta),
                                             "end": dayplan.add_min(row["end"], delta)}))


@app.route("/api/day/<bid>", methods=["DELETE"])
def api_day_delete(bid):
    return jsonify({"ok": db.day_block_delete(bid)})


@app.route("/api/day", methods=["POST"])
def api_day_add():
    """Ad-hoc block (e.g. an interview) added by hand."""
    import dayplan
    body = request.json or {}
    if not body.get("start") or not body.get("date"):
        return jsonify({"ok": False, "error": "date + start required"}), 400
    body.setdefault("cat", "review")
    body.setdefault("end", dayplan.add_min(body["start"], body.get("min") or 60))
    body.setdefault("title", dayplan.CATS.get(body["cat"], {}).get("label", body["cat"]))
    return jsonify(db.day_block_create(body))


@app.route("/api/schedule", methods=["GET"])
def api_schedule_get():
    import dayplan
    return jsonify({**dayplan.load_schedule(), "cats": dayplan.CATS})


@app.route("/api/schedule", methods=["PUT"])
def api_schedule_put():
    import dayplan
    return jsonify(dayplan.save_schedule(request.json or {}))


# ── profile links checklist ────────────────────────────────────────────────────

@app.route("/api/links", methods=["GET"])
def api_links_get():
    return jsonify(db.links_all())


@app.route("/api/links/<lid>", methods=["PUT"])
def api_links_put(lid):
    body = request.json or {}
    if body.get("status") not in (None, "todo", "in_progress", "done"):
        return jsonify({"ok": False, "error": "invalid status"}), 400
    row = db.link_update(lid, body)
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    # 5/5 done → tick the sprint milestone automatically.
    # `links and` guards all([]) == True: unreachable via this route today
    # (link_update returned a row, so >=1 link exists) but free to be safe.
    links = db.links_all()
    if links and all(l.get("status") == "done" for l in links):
        for m in db.milestones_all():
            if "profile links complete" in (m.get("text") or "").lower() and not m.get("done"):
                db.milestone_update(m["id"], {"done": 1})
    return jsonify(row)


# ── project inventory + interview stories ──────────────────────────────────────

@app.route("/api/projects", methods=["GET"])
def api_projects_get():
    return jsonify(projects.all_grouped())


@app.route("/api/projects", methods=["POST"])
def api_projects_post():
    body = request.json or {}
    if not (body.get("name") or "").strip():
        return jsonify({"ok": False, "error": "name required"}), 400
    return jsonify(projects.decorate(db.project_add(body)))


@app.route("/api/projects/<pid>", methods=["PUT"])
def api_projects_put(pid):
    row = db.project_update(pid, request.json or {})
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(projects.decorate(row))


@app.route("/api/projects/<pid>", methods=["DELETE"])
def api_projects_delete(pid):
    if not db.project_delete(pid):
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/projects/<pid>/tier", methods=["PUT"])
def api_projects_tier(pid):
    tier = (request.json or {}).get("tier")
    if tier not in ("core", "other"):
        return jsonify({"ok": False, "error": "invalid tier"}), 400
    row = projects.set_tier(pid, tier)
    if not row:
        return jsonify({"ok": False, "error": "not found"}), 404
    return jsonify(row)


@app.route("/api/projects/export", methods=["POST"])
def api_projects_export():
    return jsonify({"ok": True, "path": projects.export_markdown()})


@app.route("/api/projects/<pid>/draft", methods=["POST"])
def api_projects_draft(pid):
    try:
        return jsonify(projects.draft(pid))
    except projects.DraftError as e:
        return jsonify({"ok": False, "error": e.message}), e.status


# ── side revenue / clips log ───────────────────────────────────────────────────

@app.route("/api/side", methods=["GET"])
def api_side_get():
    limit = request.args.get("limit", type=int)
    return jsonify(db.side_all(limit))


@app.route("/api/side", methods=["POST"])
def api_side_post():
    return jsonify(db.side_create(request.json or {}))


@app.route("/api/side/<sid>", methods=["DELETE"])
def api_side_delete(sid):
    return jsonify({"ok": db.side_delete(sid)})


@app.route("/api/side/summary", methods=["GET"])
def api_side_summary():
    return jsonify(db.side_summary())


# ── personal health (weight, workouts, daily routine) ────────────────────

@app.route("/api/health", methods=["GET"])
def api_health_get():
    import health
    return jsonify(health.payload())


@app.route("/api/health/<day>", methods=["PUT"])
def api_health_day_put(day):
    return jsonify(db.health_day_upsert(day, request.json or {}))


@app.route("/api/health/workouts", methods=["GET"])
def api_health_workouts_get():
    return jsonify(db.workouts_all(request.args.get("split")))


@app.route("/api/health/workouts", methods=["POST"])
def api_health_workouts_post():
    body = request.json or {}
    if not (body.get("name") or "").strip():
        return jsonify({"error": "name is required"}), 400
    return jsonify(db.workout_create(body))


@app.route("/api/health/workouts/<wid>", methods=["PUT"])
def api_health_workouts_put(wid):
    return jsonify(db.workout_update(wid, request.json or {}))


@app.route("/api/health/workouts/<wid>", methods=["DELETE"])
def api_health_workouts_delete(wid):
    return jsonify({"ok": db.workout_delete(wid)})


@app.route("/api/health/goal", methods=["PUT"])
def api_health_goal_put():
    from agent.config import save_settings
    body = request.json or {}
    keys = ("weight_goal", "weight_start", "weight_mode",
            "height_in", "birth_year", "sex", "daily_delta", "goal_date")
    patch = {k: body[k] for k in keys if k in body}
    save_settings(patch)
    import health
    return jsonify({**health.goal(), "energy": health.energy()})


# ── Google Calendar push (one-way) ──────────────────────────────────────────────

@app.route("/api/gcal/status", methods=["GET"])
def api_gcal_status():
    import gcal
    return jsonify(gcal.status())


@app.route("/api/gcal/connect", methods=["POST"])
def api_gcal_connect():
    import gcal
    try:
        return jsonify(gcal.connect())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/day/sync-gcal", methods=["POST"])
def api_day_sync_gcal():
    import gcal
    body = request.json or {}
    try:
        return jsonify(gcal.sync_day(_parse_day(body.get("date"))))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ── legacy aliases — timeline/dashboard still call /api/controls and /api/ml ────

@app.route("/api/controls", methods=["GET"])
def api_controls_get():
    return jsonify(registry.load_track("controls") or {})


@app.route("/api/controls/week/<int:week_id>", methods=["PUT"])
def api_controls_week_put(week_id):
    return api_track_week_put("controls", week_id)


@app.route("/api/ml", methods=["GET"])
def api_ml_get():
    return jsonify(registry.load_track("ml") or {})


@app.route("/api/ml/week/<int:week_id>", methods=["PUT"])
def api_ml_week_put(week_id):
    return api_track_week_put("ml", week_id)


# ── main ───────────────────────────────────────────────────────────────────────

_DIST_DIR = Path(__file__).parent / "static" / "dist"
_DIST_INDEX = _DIST_DIR / "index.html"


@app.route("/")
def index():
    if _DIST_INDEX.exists():
        return send_file(_DIST_INDEX)
    return Response(
        "Ascent UI build missing — run `bun run build` in career-planner/frontend.",
        status=503, mimetype="text/plain")


@app.after_request
def _cache_hashed_assets(resp):
    """Vite gives every built asset a content hash, so they can be cached forever
    — without this WebView2 revalidates each one (a 304 round-trip) on every
    launch. index.html is deliberately left uncached so new builds are picked up."""
    if request.path.startswith("/static/dist/assets/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print("Ascent API - http://localhost:5000")
    app.run(debug=debug, port=5000)
