import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import plan  # noqa: E402
import registry  # noqa: E402

STEP = re.compile(r"^\[(\d+)m\] ")
PHASE_LAST = {"P1": 2, "P2": 4, "P3": 6, "P4": 9, "P5": 11, "P6": 12}


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    with db.get_conn() as conn:  # a fresh DB must not carry old ml progress
        conn.execute("DELETE FROM track_week_status WHERE track='ml'")
    yield


def _track():
    return registry.load_track("ml")


def test_header():
    t = _track()
    assert str(t["started"]) == "2026-09-28"
    assert t["daily_hours"] == 2 and t["days"] == ["Mon", "Tue", "Wed", "Thu", "Fri"] and t["active"] is True


def test_12_weeks_with_phases():
    weeks = _track()["weeks"]
    assert [w["id"] for w in weeks] == list(range(1, 13))
    for ph, last in PHASE_LAST.items():
        ids = [w["id"] for w in weeks if w["phase"] == ph]
        assert ids and max(ids) == last


@pytest.mark.parametrize("wid", range(1, 13))
def test_week_deliverables(wid):
    w = next(w for w in _track()["weeks"] if w["id"] == wid)
    assert w["est_hours"] == 10 and w["can_explain"] and w["objective"]
    mins = []
    for d in w["deliverables"]:
        m = STEP.match(d)
        assert m, f"W{wid} bad step format: {d!r}"
        assert int(m.group(1)) <= 45, f"W{wid} step over 45 min: {d!r}"
        mins.append(int(m.group(1)))
    assert 540 <= sum(mins) <= 660, f"W{wid} totals {sum(mins)} min"
    assert STEP.sub("", w["deliverables"][-1]).startswith("SHIP GATE: ")


def test_fleet_number_matches_resume_v9():
    text = (ROOT / "tracks" / "ml.yaml").read_text(encoding="utf-8")
    assert "180+" not in text and "200" in text


def test_plan_projects_ml_from_sep_28_at_10h(monkeypatch):
    monkeypatch.setattr(plan, "sprint_start", lambda today=None: date(2026, 9, 14))
    s = plan.schedule(date(2026, 9, 28))["ml"]
    assert s["start"] == date(2026, 9, 28) and s["hours_per_week"] == 10


import importlib.util

_spec = importlib.util.spec_from_file_location("migrate_ml_track_v2", ROOT / "scripts" / "migrate_ml_track_v2.py")
mig = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mig)

OLD_MS = ["ML computer-vision phase complete (weeks 1–6)", "Ship YOLOv8 + Hailo-8 portfolio demo",
          "ML LLM phase complete (Zero to Hero, weeks 7–18)"]


def _legacy_state():
    for t in OLD_MS:
        db.milestone_create({"text": t, "due": "2026-11-08"})
    db.track_set_week("ml", 1, "completed")
    db.track_set_week("ml", 2, "in_progress")
    with db.get_conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS ml_progress (week_id INTEGER PRIMARY KEY, status TEXT, "
                     "started_at TEXT, completed_at TEXT, notes TEXT, updated_at TEXT)")
        conn.execute("INSERT OR REPLACE INTO ml_progress (week_id, status) VALUES (1, 'completed')")


def test_dry_run_changes_nothing():
    _legacy_state()
    mig.run(apply=False, today=date(2026, 9, 28))
    assert db.track_status_all("ml")
    assert any(m["text"] == OLD_MS[0] for m in db.milestones_all())


def test_apply_clears_progress_for_good():
    _legacy_state()
    mig.run(apply=True, today=date(2026, 9, 28))
    db.init_db()  # the legacy ml_progress backfill must not resurrect week 1
    assert db.track_status_all("ml") == {}


EXPECTED_DUES = ["2026-10-09", "2026-10-23", "2026-11-06", "2026-11-27", "2026-12-11", "2026-12-18"]


@pytest.mark.parametrize("today", [date(2026, 9, 23), date(2026, 9, 28)])
def test_apply_replaces_milestones_projects_cert_idempotently(monkeypatch, today):
    monkeypatch.setattr(plan, "sprint_start", lambda today=None: date(2026, 9, 14))
    _legacy_state()
    for _ in range(2):
        mig.run(apply=True, today=today)
    texts = [m["text"] for m in db.milestones_all()]
    assert not any(t in texts for t in OLD_MS)
    ml = [t for t in texts if t.startswith("ML P")]
    assert len(ml) == 6 and ml[0].startswith("ML P1 complete")
    dues = [m["due"] for m in db.milestones_all() if m["text"].startswith("ML P")]
    assert dues == EXPECTED_DUES  # ML v2 starts 2026-09-28, 10h/wk, progress cleared before projecting
    slugs = [p["slug"] for p in db.projects_all()]
    assert slugs.count("fleet-anomaly") == 1 and slugs.count("maintenance-copilot") == 1
    assert all(p["tier"] == "core" for p in db.projects_all() if p["slug"] in ("fleet-anomaly", "maintenance-copilot"))
    cca = [c for c in db.certs_all() if c["title"].startswith("Claude Certified Architect")]
    assert len(cca) == 1 and cca[0]["verdict"] == "LATER" and cca[0]["status"] == "wishlist"


def test_dl_spec_cut_verdict_set_once_then_left_alone(monkeypatch):
    monkeypatch.setattr(plan, "sprint_start", lambda today=None: date(2026, 9, 14))
    c = db.cert_create({"title": "DeepLearning.AI ML + DL Spec."})
    monkeypatch.setattr(mig, "DL_SPEC_ID", c["id"])
    mig.run(apply=True, today=date(2026, 9, 23))
    got = db.cert_get(c["id"])
    assert got["verdict"] == "CUT"
    assert got["verdict_reason"] == "Supplement, not a substitute for projects"


def test_dl_spec_cut_verdict_not_overwritten_on_rerun(monkeypatch):
    monkeypatch.setattr(plan, "sprint_start", lambda today=None: date(2026, 9, 14))
    c = db.cert_create({"title": "DeepLearning.AI ML + DL Spec."})
    monkeypatch.setattr(mig, "DL_SPEC_ID", c["id"])
    db.cert_seed_fields(c["id"], {"verdict": "CUT", "verdict_reason": "custom reason from a later seed"})
    log = mig.run(apply=True, today=date(2026, 9, 23))
    assert not any(c["id"] in line for line in log)
    got = db.cert_get(c["id"])
    assert got["verdict"] == "CUT"
    assert got["verdict_reason"] == "custom reason from a later seed"  # survives regardless of run order


def test_dry_run_preview_matches_apply_and_leaves_db_untouched(monkeypatch):
    monkeypatch.setattr(plan, "sprint_start", lambda today=None: date(2026, 9, 14))
    _legacy_state()
    today = date(2026, 9, 23)
    db_path = db.DB_PATH
    before_milestones = db.milestones_all()
    before_status = db.track_status_all("ml")
    before_projects = db.projects_all()
    before_certs = db.certs_all()

    preview_log = mig.dry_run_preview(today)

    assert db.DB_PATH == db_path  # restored, not left pointed at the throwaway copy
    # a checkpoint against the real db can legitimately change the file's bytes (WAL
    # merge), so compare logical row content rather than a raw file hash
    assert db.milestones_all() == before_milestones
    assert db.track_status_all("ml") == before_status
    assert db.projects_all() == before_projects
    assert db.certs_all() == before_certs
    assert db.track_status_all("ml")  # legacy progress still present — nothing was cleared for real
    assert any(m["text"] == OLD_MS[0] for m in db.milestones_all())  # old milestones still present

    preview_line = next(l for l in preview_log if l.startswith("add milestone 'ML P1"))
    preview_p1_due = preview_line.rsplit(" due ", 1)[-1]

    mig.run(apply=True, today=today)
    applied_p1_due = next(m["due"] for m in db.milestones_all() if m["text"].startswith("ML P1"))

    assert preview_p1_due == applied_p1_due == "2026-10-09"
