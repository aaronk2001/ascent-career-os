"""Tests for the logic the README advertises: Linda's tool-loop caps, the resume
tailor's number check, weekly application targets and follow-ups, the Gantt
board's data shapes, registry-driven tracks, and the network-call rules
(job search key isolation, the news switch)."""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import dayplan  # noqa: E402
import news  # noqa: E402
import plan  # noqa: E402
import registry  # noqa: E402
import timeline_board  # noqa: E402
import tracker  # noqa: E402
from agent import _loop_common, company_intel, job_search, tools  # noqa: E402
from agent.resume_tailor import _keyword_report  # noqa: E402

KEY_VARS = ("EXA_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TAVILY_API_KEY")
# Placeholder values (not real keys) so each can be traced in what gets sent.
FAKE = {k: "value-of-" + k.split("_")[0].lower() for k in KEY_VARS}


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    yield


# ── Linda's tool loop ─────────────────────────────────────────────────────────

def test_scratchpad_blocks_fourth_call_and_identical_inputs():
    sp = _loop_common.Scratchpad()
    for i in range(3):
        assert sp.can_call("tavily_search", {"query": f"q{i}"})["allowed"]
        sp.record("tavily_search", {"query": f"q{i}"}, {"success": True})
    fourth = sp.can_call("tavily_search", {"query": "q9"})
    assert not fourth["allowed"] and "3 times" in fourth["warning"]

    sp = _loop_common.Scratchpad()
    sp.record("get_career_state", {"a": 1, "b": 2}, {"success": True})
    again = sp.can_call("get_career_state", {"b": 2, "a": 1})  # same input, other key order
    assert not again["allowed"] and "identical" in again["warning"]
    assert sp.can_call("get_career_state", {"a": 2})["allowed"]


def test_write_tools_are_refused_after_web_results():
    sp = _loop_common.Scratchpad()
    assert sp.can_call("add_application", {"company": "A"})["allowed"]
    sp.record("tavily_search", {"query": "q"}, {"success": True})
    for name in _loop_common.WRITE_TOOLS:
        blocked = sp.can_call(name, {"x": 1})
        assert not blocked["allowed"] and "confirm" in blocked["warning"]
    assert sp.can_call("get_career_state", {})["allowed"]
    assert _loop_common.WRITE_TOOLS | _loop_common.UNTRUSTED_TOOLS <= {t["name"] for t in tools.get_all_tools()}


def test_a_tool_that_raises_still_counts_toward_the_cap(monkeypatch):
    def boom(inp):
        raise RuntimeError("down")
    monkeypatch.setattr(_loop_common, "get_tool", lambda name: {"execute": boom})
    sp = _loop_common.Scratchpad()
    for i in range(3):
        result, events = _loop_common.execute_tool("flaky", {"i": i}, sp)
        assert result["success"] is False and events[-1]["type"] == "tool_error"
    result, events = _loop_common.execute_tool("flaky", {"i": 99}, sp)
    assert result.get("skipped") and events[-1]["type"] == "tool_skip"


def test_loop_caps_match_the_readme():
    assert _loop_common.MAX_CALLS_PER_TOOL == 3
    assert _loop_common.MAX_ITERATIONS == 10


# ── resume tailor: every number must trace back to the master ─────────────────

def _resume(text):
    return {"summary": text}


def test_number_check_flags_changed_and_made_up_numbers():
    corpus = "kept 96% uptime across a 200-robot fleet since 2025 using yolov8".lower()
    report = _keyword_report("", _resume("Kept 97% uptime on 200 robots; cut downtime 5x"), corpus)
    assert "97%" in report["unverified"]
    assert "5x" in report["unverified"]      # "5" is inside "2025" but is not a number there
    assert "200" not in report["unverified"]


def test_number_check_accepts_numbers_from_the_master():
    corpus = "kept 96% uptime across a 200-robot fleet".lower()
    report = _keyword_report("", _resume("Held 96% uptime on a 200-robot fleet."), corpus)
    assert report["unverified"] == []


def test_number_check_does_not_match_digits_inside_words():
    corpus = "trained yolov8 models".lower()
    assert _keyword_report("", _resume("Shipped 8 models"), corpus)["unverified"] == ["8"]


# ── weekly targets and follow-ups ─────────────────────────────────────────────

def _app(company, applied, bucket="local", status="applied", **kw):
    return db.create({"company": company, "role": "Controls Engineer", "status": status, "bucket": bucket,
                      "applied_date": applied.isoformat() if applied else None, **kw})


def test_cadence_counts_this_week_from_monday_and_all_time_separately():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    _app("A", monday)                                  # this week
    _app("B", today, bucket="remote")                  # this week
    _app("C", monday - timedelta(days=1))              # last Sunday: not this week
    _app("D", today - timedelta(days=40), bucket="az")  # legacy bucket name reads as local
    cad = db.get_cadence()
    assert cad["week_total"] == 2
    assert cad["week_by_bucket"] == {"local": 1, "remote": 1}
    assert cad["by_bucket"] == {"local": 3, "remote": 1}
    assert cad["weekly_target"] == 20 and cad["bucket_targets"] == {"local": 12, "remote": 8}
    assert db.get_stats()["this_week_count"] == 2


def test_followups_first_nudge_overdue_order_and_no_reply_list():
    today = date.today()
    fresh = _app("Fresh", today)
    stale = _app("Stale", today - timedelta(days=20))
    _app("Closed", today - timedelta(days=20), status="rejected")
    assert fresh["next_action_due"] == (today + timedelta(days=3)).isoformat()  # applied + 3 days
    cad = db.get_cadence()
    queue = [(n["company"], n["overdue"]) for n in cad["needs_followup"]]
    assert queue == [("Stale", True), ("Fresh", False)]  # overdue first, closed apps skipped
    assert [n["company"] for n in cad["no_reply"]] == ["Stale"]
    assert cad["no_reply"][0]["days"] == 20

    db.update(stale["id"], {"last_contacted": today.isoformat()})  # a follow-up resets the clock
    assert db.get_cadence()["no_reply"] == []


# ── timeline board (Gantt data) ───────────────────────────────────────────────

def test_timeline_board_shapes():
    today = date.today()
    _app("Late", today - timedelta(days=10))
    b = timeline_board.board()
    assert set(b) >= {"items", "anchors", "lanes", "today", "health", "triage"}
    keys = {"id", "lane", "source", "source_id", "date", "end_date", "label", "done", "phase", "track",
            "editable", "meta"}
    assert all(set(i) == keys and i["lane"] in b["lanes"] for i in b["items"])
    assert [i["date"] for i in b["items"]] == sorted(i["date"] for i in b["items"])

    bars = [i for i in b["items"] if i["lane"] == "learning"]
    assert bars and all(i["end_date"] >= i["date"] and not i["editable"] for i in bars)
    tracks = {m["id"]: m for m in registry.metas()}
    for i in bars:
        assert i["meta"]["parked"] is (not tracks[i["track"]]["active"])
        assert i["label"].startswith(tracks[i["track"]]["short"] + " W")
    assert any(i["label"].startswith("ML W") for i in bars)  # not "Ml"

    fu = [i for i in b["items"] if i["lane"] == "follow-ups"]
    assert fu and fu[0]["meta"]["overdue"] is True and fu[0]["editable"]
    assert b["health"]["follow-ups"]["metrics"]["overdue"] == 1


# ── registry-driven tracks: a new YAML needs no code change ───────────────────

ROBOTICS_YAML = """\
title: Robotics — ROS 2 basics
short: ROS
caption: ROS 2 sprint
day_label: ROS lab
accent: "#ef4444"
active: true
daily_hours: 2
days: [Mon, Tue, Wed, Thu, Fri, Sat]
weeks:
  - id: 1
    title: Nodes and topics
    est_hours: 4
    deliverables: ["Publish a topic", "Write a subscriber"]
"""


@pytest.fixture
def robotics_track(tmp_path, monkeypatch):
    tdir = tmp_path / "tracks"
    tdir.mkdir()
    (tdir / "robotics.yaml").write_text(ROBOTICS_YAML, encoding="utf-8")
    (tdir / "parked.yaml").write_text("title: Parked\nactive: false\nweeks:\n  - id: 1\n    title: Later\n",
                                      encoding="utf-8")
    monkeypatch.setattr(registry, "TRACKS_DIR", tdir)
    monkeypatch.setattr(registry, "_PARSE_CACHE", {})
    sched = tmp_path / "schedule.yaml"
    sched.write_text('templates:\n  weekday:\n  - {start: "09:00", min: 120, cat: robotics}\n', encoding="utf-8")
    monkeypatch.setattr(dayplan, "SCHEDULE_FILE", sched)
    monkeypatch.setattr(dayplan, "_SCHED_CACHE", None)
    return tdir


def test_new_track_yaml_gets_today_block_timeline_and_rings(robotics_track):
    meta = {m["id"]: m for m in registry.metas()}
    assert meta["robotics"]["short"] == "ROS" and meta["robotics"]["caption"] == "ROS 2 sprint"
    assert meta["parked"]["active"] is False and meta["parked"]["short"] == "Parked"

    cats = dayplan.all_cats()
    assert cats["robotics"] == {"label": "ROS lab", "color": "#ef4444", "track": True}
    assert list(cats)[:2] == ["apps", "robotics"] and "parked" not in cats  # parked tracks get no Today goals

    blocks = dayplan.generate(date(2026, 9, 21))  # a Monday
    assert [b["cat"] for b in blocks] == ["robotics"]
    assert blocks[0]["title"] == "ROS: W1 Nodes and topics"
    assert "Next: Publish a topic" in blocks[0]["detail"]

    assert plan.schedule(date(2026, 9, 21))["robotics"]["active"]
    labels = [i["label"] for i in timeline_board.board()["items"] if i["track"] == "robotics"]
    assert labels == ["ROS W1: Nodes and topics"]


def test_short_name_defaults():
    assert registry.short_name("ml", {}) == "ML"
    assert registry.short_name("controls", {}) == "Controls"
    assert registry.short_name("it-pro", {"short": "IT"}) == "IT"


def test_negative_daily_hours_cannot_hang_the_planner(robotics_track):
    (robotics_track / "robotics.yaml").write_text(ROBOTICS_YAML.replace("daily_hours: 2", "daily_hours: -1"),
                                                  encoding="utf-8")
    t0 = time.monotonic()
    s = plan.schedule(date(2026, 9, 21))
    assert time.monotonic() - t0 < 5 and s["robotics"]["end"] >= date(2026, 9, 21)


# ── network calls: key isolation, fail-soft job search, news switch ───────────

class _Resp:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def _set_keys(monkeypatch, *names):
    for k in KEY_VARS:
        monkeypatch.delenv(k, raising=False)
    for k in names:
        monkeypatch.setenv(k, FAKE[k])


def _capture_posts(monkeypatch, payload):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        return _Resp(payload)
    monkeypatch.setattr(job_search.requests, "post", fake_post)
    monkeypatch.setattr(tools.requests, "post", fake_post)
    return calls


def test_job_search_never_sends_another_providers_key(monkeypatch):
    _set_keys(monkeypatch, *KEY_VARS[1:])
    calls = _capture_posts(monkeypatch, {"results": []})
    out = job_search.scan_jobs()
    assert out == {"ok": False, "error": job_search.NOT_CONFIGURED, "jobs": []}
    assert calls == []  # no Exa key: nothing is sent anywhere, and no mock jobs come back

    intel = company_intel.research_company("Acme")
    assert intel["recent_news"] == [] and "EXA_API_KEY" in intel["news_note"] and calls == []


def test_exa_gets_only_the_exa_key(monkeypatch):
    _set_keys(monkeypatch, *KEY_VARS)
    hit = {"title": "Controls Engineer - Acme Robotics", "url": "https://jobs.example/1",
           "text": "robotics automation engineer, PLC, python"}
    calls = _capture_posts(monkeypatch, {"results": [hit]})
    out = job_search.scan_jobs(["controls engineer jobs Denver"])
    assert out["ok"] and out["jobs"][0]["company"] == "Acme Robotics" and out["jobs"][0]["source"] == "exa"
    (url, kw), = calls
    assert url == "https://api.exa.ai/search"
    assert kw["headers"] == {"x-api-key": FAKE["EXA_API_KEY"]}
    sent = repr(kw)
    assert not any(FAKE[k] in sent for k in KEY_VARS[1:])


def test_tavily_gets_only_the_tavily_key(monkeypatch):
    _set_keys(monkeypatch, "EXA_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY")
    calls = _capture_posts(monkeypatch, {"results": []})
    assert tools._tavily_search_tool({"query": "plc jobs"})["success"]
    (url, kw), = calls
    assert url == "https://api.tavily.com/search" and kw["json"]["api_key"] == FAKE["TAVILY_API_KEY"]
    assert FAKE["EXA_API_KEY"] not in repr(kw) and FAKE["OPENAI_API_KEY"] not in repr(kw)


def test_search_jobs_tool_and_scan_route_fail_soft(monkeypatch):
    _set_keys(monkeypatch)
    res = tools.get_tool("search_jobs")["execute"]({"query": "controls engineer"})
    assert res["success"] is False and "EXA_API_KEY" in res["error"] and "tavily_search" in res["error"]
    tracker.app.config.update(TESTING=True, ASCENT_PORTS={5001})
    r = tracker.app.test_client().post("/api/jobs/scan", headers={"Host": "127.0.0.1:5001"})
    assert r.status_code == 503 and r.get_json() == {"ok": False, "error": job_search.NOT_CONFIGURED, "jobs": []}
    tracker.app.config.pop("ASCENT_PORTS", None)


def test_no_code_is_imported_from_outside_the_repo():
    src = (ROOT / "agent" / "tools.py").read_text(encoding="utf-8")
    assert "job-search-agent" not in src and "sys.path.insert" not in src.split("import db", 1)[1]


def test_news_is_off_by_default_and_fetches_nothing(monkeypatch):
    fetched = []
    monkeypatch.setattr(news, "_fetch", lambda topic: fetched.append(topic) or [])
    assert news.get_news(["robotics"]) == {"items": [], "errors": {}, "disabled": True}
    assert fetched == []
    monkeypatch.setattr(news, "enabled", lambda: True)
    assert news.get_news(["robotics"])["items"] == [] and fetched == ["robotics"]
