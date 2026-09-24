"""Data-driven track registry. Each curriculum is a `tracks/<id>.yaml` file.
Adding a track = dropping a YAML in tracks/ — no code changes.
"""
import copy
from pathlib import Path

import yaml

import db
import yamlio

TRACKS_DIR = Path(__file__).parent / "tracks"

# Parsed-YAML cache keyed by mtime — track YAML rarely changes but was being
# re-parsed on every /api/tracks/<id> hit (ml ~2s, controls ~0.8s each call).
_PARSE_CACHE: dict[str, tuple[float, dict]] = {}

# defaults applied when a track yaml omits the metadata key
CATEGORY = {
    "controls": "controls", "ml": "ml", "welding": "welding",
    "mechanical-design": "mechanical", "it-pro": "it",
}
ACCENT = {
    "controls": "#3b82f6", "ml": "#8b5cf6", "welding": "#f59e0b",
    "mechanical-design": "#10b981", "it-pro": "#06b6d4",
}
SCHEDULED = {"controls", "ml"}  # fixed cadence; everything else is "flexible/explore"


def _files():
    return sorted(TRACKS_DIR.glob("*.yaml")) if TRACKS_DIR.exists() else []


def _load_file(tid):
    p = TRACKS_DIR / f"{tid}.yaml"
    if not p.exists():
        return None
    mtime = p.stat().st_mtime
    cached = _PARSE_CACHE.get(tid)
    if not cached or cached[0] != mtime:
        with open(p, encoding="utf-8") as f:
            cached = (mtime, yaml.load(f, Loader=yamlio.LOADER) or {})
        _PARSE_CACHE[tid] = cached
    # deepcopy: callers mutate the returned dict (merge DB progress, _meta)
    return copy.deepcopy(cached[1])


def exists(tid):
    return (TRACKS_DIR / f"{tid}.yaml").exists()


def track_ids():
    return [p.stem for p in _files()]


def _meta(tid, data):
    return {
        "id": tid,
        "title": data.get("title") or tid,
        "category": data.get("category") or CATEGORY.get(tid, "general"),
        "schedule": data.get("schedule") or ("scheduled" if tid in SCHEDULED else "flexible"),
        "accent": data.get("accent") or ACCENT.get(tid, "#6366f1"),
        "icon": data.get("icon"),
        "lab_dir": data.get("lab_dir"),
        "cadence": data.get("cadence"),
        "target_completion": data.get("target_completion"),
        "active": bool(data.get("active", True)),
        "daily_hours": data.get("daily_hours"),
        "days": data.get("days"),
        "resume_after": data.get("resume_after"),
    }


def load_track(tid):
    """Static track yaml merged with live per-week DB progress, or None if absent."""
    data = _load_file(tid)
    if data is None:
        return None
    status = db.track_status_all(tid)
    detail = db.track_detail_all(tid)
    for week in data.get("weeks", []):
        live = status.get(week["id"])
        if live:
            week["status"] = live.get("status", week.get("status"))
            week["started_at"] = live.get("started_at")
            week["completed_at"] = live.get("completed_at")
            week["notes"] = live.get("notes")
        d = detail.get(week["id"])
        week["objectives_done"] = d["objectives_done"] if d else []
        week["can_explain_done"] = d["can_explain_done"] if d else []
        week["hours"] = d["hours"] if d else 0
    data.update(_meta(tid, data))
    return data


def _summary(tid):
    data = _load_file(tid) or {}
    status = db.track_status_all(tid)
    weeks = data.get("weeks", [])
    done = active = 0
    for w in weeks:
        st = (status.get(w["id"]) or {}).get("status", w.get("status", "not_started"))
        if st == "completed":
            done += 1
        elif st == "in_progress":
            active += 1
    m = _meta(tid, data)
    n = len(weeks)
    m.update({"weeks": n, "done": done, "active_weeks": active,
              "pct": round(done / n * 100) if n else 0})
    return m


def all_tracks():
    return [_summary(p.stem) for p in _files()]
