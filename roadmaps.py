"""Data-driven roadmaps + job-fit engine.

Each roadmap is a `data/roadmaps/<id>.json` tree (sections -> nodes); live node
state lives in the `roadmap_progress` table and is merged on load (same
static-file + DB-progress pattern as registry.py).

Each target role is a `data/job_profiles/<id>.json` profile (required skills +
levels + certs). `gap_analysis` matches a profile against the tracked skill
proficiencies to produce a match% and a gap-driven study list.

All roadmap *content* is original (the roadmap.sh taxonomy is reused for
structure only — see the overhaul plan's licensing note).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import db

ROADMAPS_DIR = Path(__file__).parent / "data" / "roadmaps"
PROFILES_DIR = Path(__file__).parent / "data" / "job_profiles"

VALID_STATES = {"locked", "available", "in_progress", "mastered"}
# Ids come from URLs; on Windows a backslash in one would otherwise escape the data folder.
_ID_RE = re.compile(r"[A-Za-z0-9_-]+")


def _load_json(path: Path):
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _roadmap_files():
    return sorted(ROADMAPS_DIR.glob("*.json")) if ROADMAPS_DIR.exists() else []


def _profile_files():
    return sorted(PROFILES_DIR.glob("*.json")) if PROFILES_DIR.exists() else []


def _nodes(data):
    for sec in data.get("sections", []):
        for node in sec.get("nodes", []):
            yield node


# ── roadmaps ────────────────────────────────────────────────────────────────────
def load_roadmap(rid):
    """Static tree merged with live per-node state, or None if absent."""
    if not _ID_RE.fullmatch(str(rid)):
        return None
    data = _load_json(ROADMAPS_DIR / f"{rid}.json")
    if data is None:
        return None
    progress = db.roadmap_progress_all(rid)
    data["id"] = rid
    for node in _nodes(data):
        live = progress.get(node["id"])
        node["state"] = (live or {}).get("state") or node.get("state") or "available"
        node["notes"] = (live or {}).get("notes")
    return data


def _summary(rid):
    data = _load_json(ROADMAPS_DIR / f"{rid}.json") or {}
    progress = db.roadmap_progress_all(rid)
    nodes = list(_nodes(data))
    counts = {"mastered": 0, "in_progress": 0, "available": 0, "locked": 0}
    for n in nodes:
        st = (progress.get(n["id"]) or {}).get("state") or n.get("state") or "available"
        counts[st] = counts.get(st, 0) + 1
    total = len(nodes)
    return {
        "id": rid,
        "title": data.get("title") or rid,
        "description": data.get("description"),
        "accent": data.get("accent"),
        "nodes": total,
        "mastered": counts["mastered"],
        "in_progress": counts["in_progress"],
        "pct": round(counts["mastered"] / total * 100) if total else 0,
    }


def all_roadmaps():
    return [_summary(p.stem) for p in _roadmap_files()]


# ── job profiles + match engine ─────────────────────────────────────────────────
def _profile_summary(pid):
    data = _load_json(PROFILES_DIR / f"{pid}.json") or {}
    return {
        "id": pid,
        "title": data.get("title") or pid,
        "summary": data.get("summary"),
        "bucket": data.get("bucket"),
        "required_skills": data.get("required_skills", []),
        "certs": data.get("certs", []),
    }


def all_profiles():
    return [_profile_summary(p.stem) for p in _profile_files()]


def load_profile(pid):
    if not _ID_RE.fullmatch(str(pid)):
        return None
    data = _load_json(PROFILES_DIR / f"{pid}.json")
    if data is None:
        return None
    data["id"] = pid
    return data


def gap_analysis(pid):
    """Match tracked skill proficiencies against a profile's required levels.

    match% is weighted coverage: sum(min(current, required)) / sum(required).
    Each row reports current vs required, the gap, and whether it's met.
    """
    profile = load_profile(pid)
    if profile is None:
        return None
    by_name = {(s.get("skill") or "").strip().lower(): s for s in db.skills_all()}
    rows, have, need = [], 0, 0
    for req in profile.get("required_skills", []):
        name = (req.get("skill") or "").strip()
        level = int(req.get("level") or 0)
        match = by_name.get(name.lower())
        current = int((match or {}).get("proficiency") or 0)
        gap = max(0, level - current)
        have += min(current, level)
        need += level
        rows.append({
            "skill": name, "required": level, "current": current, "gap": gap,
            "met": current >= level and level > 0, "tracked": match is not None,
            "skill_id": (match or {}).get("id"),
        })
    rows.sort(key=lambda r: (-r["gap"], r["skill"].lower()))
    met = sum(1 for r in rows if r["met"])
    return {
        "profile": {"id": pid, "title": profile.get("title"), "summary": profile.get("summary"),
                    "bucket": profile.get("bucket"), "certs": profile.get("certs", [])},
        "match_pct": round(have / need * 100) if need else 0,
        "met": met, "total": len(rows), "gaps": rows,
    }
