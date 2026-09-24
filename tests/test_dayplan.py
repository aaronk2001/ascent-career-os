import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import dayplan  # noqa: E402
import projects  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    monkeypatch.setattr(dayplan, "load_settings", lambda: {"daily_apps": 4, "bridge_mode": False})
    yield


def test_add_min_and_minutes_between():
    assert dayplan.add_min("08:30", 120) == "10:30"
    assert dayplan.add_min("23:50", 20) == "00:10"
    assert dayplan.minutes_between("08:30", "10:30") == 120


def test_template_selection():
    assert dayplan.template_name(date(2026, 9, 10), {"bridge_mode": False}) == "weekday"
    assert dayplan.template_name(date(2026, 9, 10), {"bridge_mode": True}) == "bridge_weekday"
    assert dayplan.template_name(date(2026, 9, 12), {}) == "saturday"
    assert dayplan.template_name(date(2026, 9, 13), {}) == "sunday"


def test_generate_is_idempotent_and_keeps_done_on_force():
    d = date(2026, 9, 10)
    first = dayplan.generate(d)
    active = dayplan.active_cats()
    assert [b["cat"] for b in first] == [e["cat"] for e in dayplan.load_schedule()["templates"]["weekday"]
                                         if e["cat"] in active]
    assert all(b["end"] > b["start"] for b in first)
    assert first[0]["title"].startswith("Apply: 4")
    assert dayplan.generate(d) == first

    db.day_block_update(first[1]["id"], {"status": "done", "actual_min": 90})
    regen = dayplan.generate(d, force=True)
    kept = [b for b in regen if b["id"] == first[1]["id"]]
    assert kept and kept[0]["status"] == "done" and kept[0]["actual_min"] == 90
    assert len(regen) == len(first)


def test_sunday_generates_no_blocks():
    assert dayplan.generate(date(2026, 9, 13)) == []


def test_week_summary_totals():
    dayplan.generate(date(2026, 9, 10))
    blocks = db.day_blocks_for("2026-09-10")
    db.day_block_update(blocks[0]["id"], {"status": "done", "actual_min": 100})
    ws = dayplan.week_summary(date(2026, 9, 7))
    assert ws["totals"]["apps"] == {"planned": 120, "actual": 100, "done": 1, "blocks": 1}
    assert "break" not in ws["totals"]


def test_profile_links_seeded_and_portfolio_block_points_at_next_link():
    links = db.links_all()
    assert [l["key"] for l in links] == ["linkedin", "github", "portfolio", "other"]
    assert all(l["due"] is None and l["status"] == "todo" for l in links)  # no personal dates
    blocks = dayplan.generate(date(2026, 9, 10))
    pf = next(b for b in blocks if b["cat"] == "portfolio")
    assert "LinkedIn" in pf["title"] and "due None" not in pf["detail"]
    github = next(l for l in links if l["key"] == "github")
    db.link_update(github["id"], {"due": "2026-09-12"})
    pf = dayplan._fill_portfolio()
    assert "GitHub" in pf[0] and "due 2026-09-12" in pf[1]  # earliest-due open link wins


def test_side_summary_streak():
    db.side_create({"date": "2026-09-09", "platform": "tiktok", "posts": 2, "followers": 40})
    db.side_create({"date": "2026-09-10", "platform": "tiktok", "posts": 3, "followers": 55, "revenue": 1.5})
    s = db.side_summary(date(2026, 9, 10))
    assert s["streak_days"] == 2
    assert s["latest_followers"]["tiktok"]["followers"] == 55
    assert s["posts_total"] == 5 and s["revenue_total"] == 1.5


def test_templates_have_project_cert_and_ml_120():
    t = dayplan.load_schedule()["templates"]
    for name in ("weekday", "saturday"):
        cats = {b["cat"]: b for b in t[name]}
        assert cats["project"]["min"] == 45 and cats["cert"]["min"] == 45
    assert next(b for b in t["weekday"] if b["cat"] == "ml")["min"] == 120


def test_study_plan_no_longer_emits_ignition():
    assert "ignition" not in dayplan.STUDY_PLAN.values()
    for wd in range(7):
        title, *_ = dayplan._fill_study(date(2026, 9, 21 + wd))
        assert "Ignition" not in title


def _add_core_projects(n=6):
    return [db.project_add({"name": f"P{i}", "slug": f"p{i}", "tier": "core", "sort": i}) for i in range(n)]


def test_fill_project_picks_closest_to_shipped():
    core = _add_core_projects()
    db.project_update(core[3]["id"], {"ship": {"repo": True, "readme": True}})
    db.project_update(core[5]["id"], {"ship": {"repo": True}})
    title, detail, link, kind, sid = dayplan._fill_project()
    assert sid == core[3]["id"] and kind == "project"
    assert "Demo video / photos" in title
    assert link == f"#/projects?open={core[3]['id']}"


def test_fill_project_all_shipped_falls_back_to_story():
    _add_core_projects(2)
    for r in db.projects_all():
        if r["tier"] == "core":
            db.project_update(r["id"], {"ship": {k: True for k, _ in projects.SHIP_ITEMS}})
    title, *_ = dayplan._fill_project()
    assert title.startswith("Project: all core shipped")


def test_fill_cert_soonest_exam_with_open_steps():
    db.cert_create({"title": "Later exam", "status": "in_progress", "exam_date": "2026-12-01",
                        "steps": [{"text": "a1", "hours": 1}]})
    b = db.cert_create({"title": "Soon exam", "status": "in_progress", "exam_date": "2026-10-02",
                        "steps": [{"text": "b1", "hours": 1, "done": True}, {"text": "b2", "hours": 1}]})
    db.cert_create({"title": "No steps", "status": "in_progress", "exam_date": "2026-09-30"})
    title, detail, link, kind, sid = dayplan._fill_cert(date(2026, 9, 23))
    assert sid == b["id"] and "b2" in title and link == f"#/certs?open={b['id']}"
    assert "d to exam" in detail


def test_fill_cert_fallback():
    title, _, link, *_ = dayplan._fill_cert(date(2026, 9, 23))
    assert title == "Cert: pick a cert & set an exam date" and link == "#/certs"


def test_fill_project_without_projects_points_at_projects():
    title, _, link, *_ = dayplan._fill_project()
    assert title == "Project: promote a core project" and link == "#/projects"


def _with_modules(monkeypatch, **on):
    s = {"daily_apps": 4, "bridge_mode": False, "modules": on}
    monkeypatch.setattr(dayplan, "load_settings", lambda: s)
    return s


def test_disabled_modules_skip_their_blocks(monkeypatch):
    sched = {"wake": "07:00", "hard_stop": "21:00", "templates": {"weekday": [
        {"start": "08:00", "min": 60, "cat": "apps"}, {"start": "09:00", "min": 30, "cat": "clips"},
        {"start": "10:00", "min": 60, "cat": "gym"}, {"start": "11:00", "min": 30, "cat": "review"}]}}
    monkeypatch.setattr(dayplan, "load_schedule", lambda: sched)
    _with_modules(monkeypatch)  # defaults: every optional module off
    assert [b["cat"] for b in dayplan.generate(date(2026, 9, 10))] == ["apps", "review"]
    assert set(dayplan.day_payload(date(2026, 9, 10))["cats"]).isdisjoint({"clips", "gym", "bridge"})

    _with_modules(monkeypatch, clips=True, health=True)
    cats = [b["cat"] for b in dayplan.generate(date(2026, 9, 10), force=True)]
    assert cats == ["apps", "clips", "gym", "review"]


def test_payload_hides_blocks_of_a_module_switched_off_later(monkeypatch):
    _with_modules(monkeypatch, health=True)
    db.day_block_create({"date": "2026-09-10", "start": "18:00", "end": "19:00", "cat": "gym", "title": "Gym"})
    assert any(b["cat"] == "gym" for b in dayplan.day_payload(date(2026, 9, 10))["blocks"])
    _with_modules(monkeypatch)
    assert not any(b["cat"] == "gym" for b in dayplan.day_payload(date(2026, 9, 10))["blocks"])
    assert "gym" not in dayplan.week_summary(date(2026, 9, 7))["totals"]


def test_repeated_track_blocks_get_distinct_goals(monkeypatch):
    track = {"weeks": [{"id": 1, "title": "Toolchain", "status": "in_progress",
                        "deliverables": ["Install IDE", "First ladder rung", "Record demo"]}]}
    monkeypatch.setattr(dayplan.registry, "load_track", lambda tid: track)
    first = dayplan._fill_track("controls", "Controls", 0)
    second = dayplan._fill_track("controls", "Controls", 1)
    assert first[0] != second[0] and "Install IDE" in first[1] and "First ladder rung" in second[1]


def test_study_topics_and_courses_come_from_settings():
    s = {"study_plan": {5: "trading"}, "study_topics": {"trading": ["Markets", "Read one filing."]},
         "social_courses": ["Course A"]}
    assert dayplan._fill_study(date(2026, 9, 26), s)[0] == "Study: Markets"  # a Saturday
    assert dayplan._fill_study(date(2026, 9, 26))[0] == "Study: PLC theory"
    assert "Course A" in dayplan._fill_social(date(2026, 9, 26), s)[1]


def test_shipped_code_has_no_personal_study_topics():
    blob = repr((dayplan.STUDY_TOPICS, dayplan.SOCIAL_COURSE_ROTATION)).lower()
    assert "trading" not in blob
