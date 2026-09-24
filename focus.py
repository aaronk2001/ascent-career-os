"""Next-action engine: ranks the highest-leverage moves toward a target role by
the plan deadline (next cert exam, else projected program end), composing
skill-gap analysis, roadmap node state, the day's learning cadence, and
certification progress. Read-only over the existing loaders."""
from __future__ import annotations

from datetime import date

import anchors
import certs as certs_mod
import db
import plan
import registry
import roadmaps

DEFAULT_PROFILE = "controls-engineer"
DEFAULT_ROADMAP = "robotics-controls"
_EST_HOURS = {"beginner": 4, "core": 8, "advanced": 12}


def _skill_node_map(roadmap):
    m = {}
    for sec in roadmap.get("sections", []):
        for n in sec.get("nodes", []):
            if n.get("skill"):
                m.setdefault(n["skill"].strip().lower(), n)
    return m


def _unlocks(roadmap, node_id):
    return sum(1 for sec in roadmap.get("sections", [])
              for n in sec.get("nodes", []) if node_id in (n.get("prereq") or []))


def _current_week(track):
    weeks = [w for w in track.get("weeks", []) if not w.get("parked")]
    return (next((w for w in weeks if w.get("status") == "in_progress"), None)
            or next((w for w in weeks if w.get("status") != "completed"), None))


def compute(profile_id=None, today=None):
    pid = profile_id or DEFAULT_PROFILE
    today = today or date.today()
    gap = roadmaps.gap_analysis(pid)
    if gap is None:
        return None
    roadmap = roadmaps.load_roadmap(DEFAULT_ROADMAP) or {"sections": []}
    smap = _skill_node_map(roadmap)
    profile_certs = [c.lower() for c in gap["profile"].get("certs", [])]
    actions = []  # "merit" actions (skills/nodes/certs), scored on a comparable scale

    # 1) skill gaps -> the roadmap node that teaches them, else raw skill practice
    for g in gap["gaps"]:
        if g["met"] or g["gap"] <= 0:
            continue
        base = g["gap"] * max(1, g["required"])
        node = smap.get(g["skill"].strip().lower())
        if node and node.get("state") != "mastered":
            actions.append({
                "type": "roadmap_node", "id": node["id"],
                "title": f"Advance: {node['title']}",
                "why": f"{g['skill']} is L{g['current']}/{g['required']} for {gap['profile']['title']} — this node builds it.",
                "deep_link": "#/roadmap",
                "raw": base + _unlocks(roadmap, node["id"]) * 2,
                "est": f"~{_EST_HOURS.get(node.get('level'), 8)}h",
            })
        else:
            actions.append({
                "type": "skill", "id": g.get("skill_id") or g["skill"],
                "title": f"Build skill: {g['skill']}",
                "why": f"L{g['current']}/{g['required']} for {gap['profile']['title']}"
                       + ("" if g["tracked"] else " — not tracked yet."),
                "deep_link": "#/skills", "raw": base, "est": "~10h",
            })

    # 2) next certification — same pick as Today (dayplan._fill_cert): in-progress
    # with an unchecked step, soonest exam_date first. Else a target-role cert from
    # the wishlist, else the backlog — skipping anything the research verdict CUT.
    cert_rows = db.certs_all()
    nxt, verb = certs_mod.next_study_cert(cert_rows, today), "Continue cert"
    if not nxt:
        not_cut = [c for c in cert_rows if c["status"] == "wishlist" and c.get("verdict") != "CUT"]
        nxt = (next((c for c in not_cut if c["title"].lower() in profile_certs), None)
               or next(iter(not_cut), None))
        verb = "Start cert"
    if nxt:
        on_path = nxt["title"].lower() in profile_certs
        actions.append({
            "type": "certification", "id": nxt["id"], "title": f"{verb}: {nxt['title']}",
            "why": "Target cert for this role." if on_path else "Next in your cert backlog.",
            "deep_link": f"#/certs?open={nxt['id']}", "raw": 12 if on_path else 5, "est": nxt.get("time_est") or "—",
        })

    # 3) today's cadence block -> the active learning week. It's the literal "do this
    # in today's session" nudge, so it leads on a study day — but only just above the
    # top merit action, so the other impact bars stay meaningful (Sun has no block).
    merit_max = max((a["raw"] for a in actions), default=1)
    tid = plan.track_for_day(today)
    if tid and registry.exists(tid):
        tr = registry.load_track(tid) or {}
        wk = _current_week(tr)
        if wk:
            hrs = tr.get("daily_hours") or 1
            actions.append({
                "type": "learning_week", "id": f"{tid}:{wk['id']}",
                "title": f"This week: {tr.get('title', tid)} — W{wk['id']} {wk['title']}",
                "why": f"Today is a {today.strftime('%a')} {tid} block ({hrs}h scheduled).",
                "deep_link": "#/today", "raw": merit_max + 5, "est": f"{hrs}h today",
            })

    tracked = {c["title"].lower() for c in cert_rows}
    missing = [c for c in gap["profile"].get("certs", []) if c.lower() not in tracked]

    actions.sort(key=lambda a: a["raw"], reverse=True)
    top = actions[:6]
    hi = max((a["raw"] for a in top), default=1)
    for a in top:
        a["impact"] = round(a.pop("raw") / hi * 100)

    return {
        "profile": {"id": pid, "title": gap["profile"]["title"], "match_pct": gap["match_pct"],
                    "met": gap["met"], "total": gap["total"]},
        "deadline": anchors.deadline().isoformat(),
        "days_left": (anchors.deadline() - today).days,
        "actions": top,
        "missing_certs": missing,
    }
