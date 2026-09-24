import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import plan  # noqa: E402
import registry  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    yield


def test_walk_consumes_hours_on_scheduled_days():
    weeks = [{"id": 1, "est_hours": 6}, {"id": 2, "est_hours": 3}]
    spans, end = plan._walk(weeks, date(2026, 9, 7), {0, 2, 4}, 3, 6)  # Mon/Wed/Fri, 3h/day
    assert spans[1] == {"start": "2026-09-07", "end": "2026-09-09"}   # Mon + Wed
    assert spans[2] == {"start": "2026-09-11", "end": "2026-09-11"}   # Fri
    assert end == date(2026, 9, 11)


def test_schedule_active_tracks_start_today_and_parked_after_offer(monkeypatch):
    monkeypatch.setattr(plan, "offer_date", lambda today=None: date(2026, 11, 15))
    monkeypatch.setattr(plan, "sprint_start", lambda today=None: date(2026, 9, 14))
    today = date(2026, 9, 23)  # on/after controls' real `started` (2026-09-23)
    s = plan.schedule(today)
    assert s["controls"]["active"] and s["controls"]["start"] <= today
    assert s["controls"]["active_end"] < date(2026, 11, 15)
    for tid in ("welding", "mechanical-design", "it-pro"):
        assert s[tid]["parked"]
        assert s[tid]["start"] >= date(2026, 11, 15)
    # ML v2 is a fully active 12-week track, so it — not controls — sets the sprint end
    assert plan.program_end(today) == s["ml"]["active_end"] > s["controls"]["active_end"]
    assert s["ml"]["active_end"] <= date(2026, 12, 31)  # 12 wk x 10 h ends 2026-12-18; 1 h/day would run into Feb
    assert plan.full_program_end(today) > date(2026, 11, 15)


def test_parked_weeks_project_after_offer(monkeypatch):
    monkeypatch.setattr(plan, "offer_date", lambda today=None: date(2026, 11, 15))
    load = registry.load_track

    def with_parked_tail(tid):  # ML v2 has no parked weeks; park its last two to exercise the rule
        t = load(tid)
        if t and tid == "ml":
            for w in t["weeks"][-2:]:
                w["parked"] = True
        return t

    monkeypatch.setattr(registry, "load_track", with_parked_tail)
    s = plan.schedule(date(2026, 9, 10))
    ml = registry.load_track("ml")
    parked = [w["id"] for w in ml["weeks"] if plan.is_parked_week(w)]
    assert parked
    assert all(s["ml"]["weeks"][w]["start"] >= "2026-11-15" for w in parked)


def test_tracks_for_day_respects_weekday():
    # dates chosen on/after both real `started` dates (controls 2026-09-23, ml 2026-09-28)
    # so neither track is gated out as "not started yet"
    assert set(plan.tracks_for_day(date(2026, 9, 30))) >= {"controls", "ml"}  # Wed
    assert plan.tracks_for_day(date(2026, 10, 4)) == []                       # Sun
    assert plan.tracks_for_day(date(2026, 10, 3)) == ["controls"]             # Sat: ML is Mon-Fri


def test_tracks_for_day_gates_future_started(monkeypatch):
    monkeypatch.setattr(plan, "sprint_start", lambda today=None: date(2026, 9, 14))
    today = date(2026, 9, 23)
    assert plan.schedule(today)["ml"]["start"] == date(2026, 9, 28)
    assert "ml" not in plan.tracks_for_day(today)
    assert "ml" in plan.tracks_for_day(date(2026, 9, 28))
