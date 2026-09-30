"""Data-driven track registry. Each curriculum is a `tracks/<id>.yaml` file.
Adding a track = dropping a YAML in tracks/ — no code changes. Everything the UI
needs comes from the file's top-level keys (see _meta): `active: false` parks a
track, `short` / `caption` label it, and a schedule.yaml block whose `cat` is the
track id becomes a Today goal for it (labelled `day_label`, coloured `day_color`).
"""
import copy
import re
from pathlib import Path

import yaml

import db
import yamlio

TRACKS_DIR = Path(__file__).parent / "tracks"
# Ids come from URLs; on Windows a backslash in one would otherwise escape tracks/.
_ID_RE = re.compile(r"[A-Za-z0-9_-]+")


def _path(tid):
    return TRACKS_DIR / f"{tid}.yaml" if _ID_RE.fullmatch(str(tid)) else None


# Parsed-YAML cache keyed by mtime — track YAML rarely changes but was being
# re-parsed on every /api/tracks/<id> hit (ml ~2s, controls ~0.8s each call).
_PARSE_CACHE: dict[str, tuple[float, dict]] = {}


def _files():
    return sorted(TRACKS_DIR.glob("*.yaml")) if TRACKS_DIR.exists() else []


def _raw(tid):
    """Cached parse of tracks/<tid>.yaml. Shared: never mutate the result."""
    p = _path(tid)
    if p is None or not p.exists():
        return None
    mtime = p.stat().st_mtime
    cached = _PARSE_CACHE.get(tid)
    if not cached or cached[0] != mtime:
        with open(p, encoding="utf-8") as f:
            cached = (mtime, yaml.load(f, Loader=yamlio.LOADER) or {})
        _PARSE_CACHE[tid] = cached
    return cached[1]


def _load_file(tid):
    # deepcopy: callers mutate the returned dict (merge DB progress, _meta)
    data = _raw(tid)
    return None if data is None else copy.deepcopy(data)


def exists(tid):
    p = _path(tid)
    return p is not None and p.exists()


def track_ids():
    return [p.stem for p in _files()]


def short_name(tid, data=None):
    """Chip label: `short:` from the YAML, else ML / Controls / It-pro style."""
    data = data if data is not None else (_raw(tid) or {})
    return str(data.get("short") or (tid.upper() if len(tid) <= 3 else tid.capitalize()))


def _meta(tid, data):
    short = short_name(tid, data)
    accent = data.get("accent") or "#6366f1"
    return {
        "id": tid,
        "title": data.get("title") or tid,
        "short": short,
        "caption": data.get("caption") or short,
        "day_label": data.get("day_label") or f"{short} track",
        "day_color": data.get("day_color") or accent,
        "category": data.get("category") or "general",
        "schedule": data.get("schedule") or "flexible",
        "accent": accent,
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


def metas():
    """Top-level metadata of every track (no DB access, no deep copy)."""
    return [_meta(p.stem, _raw(p.stem) or {}) for p in _files()]


def all_tracks():
    return [_summary(p.stem) for p in _files()]
