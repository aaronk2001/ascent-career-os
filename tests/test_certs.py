import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import anchors  # noqa: E402
import db  # noqa: E402
import certs  # noqa: E402
import dayplan  # noqa: E402
import focus  # noqa: E402
import timeline_board  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    yield


def _c(**kw):
    base = {"status": "in_progress", "exam_date": None, "steps": []}
    return {**base, **kw}


TODAY = date(2026, 9, 23)  # Wednesday


def test_pace_states():
    assert certs.pace(_c(), TODAY)["state"] == "no_plan"
    assert certs.pace(_c(steps=[{"text": "a", "hours": 1, "done": True}]), TODAY)["state"] == "done"
    assert certs.pace(_c(steps=[{"text": "a", "hours": 1, "done": False}]), TODAY)["state"] == "no_date"
    past = certs.pace(_c(exam_date="2026-09-20", steps=[{"text": "a", "hours": 1, "done": False}]), TODAY)
    assert past["state"] == "past"


def test_pace_counts_mon_to_sat_slots():
    # Wed 09-23 .. Fri 10-02 exclusive: Wed Thu Fri Sat Mon Tue Wed Thu = 8 slots -> 6.0 h
    c = _c(exam_date="2026-10-02", steps=[{"text": "a", "hours": 6, "done": False}])
    p = certs.pace(c, TODAY)
    assert p["days_left"] == 9 and p["slot_hours"] == 6.0 and p["state"] == "on_pace"
    c["steps"][0]["hours"] = 6.5
    assert certs.pace(c, TODAY)["state"] == "behind"


def test_budget():
    rows = [
        {"status": "in_progress", "cost_usd": 100, "exam_date": "2026-10-02"},
        {"status": "in_progress", "cost_usd": 300, "exam_date": "2026-12-01"},
        {"status": "in_progress", "cost_usd": None, "exam_date": None},
        {"status": "wishlist", "cost_usd": 999, "exam_date": "2026-10-01"},
    ]
    b = certs.budget(rows, "2026-11-10", 800)
    assert b == {"active_total": 400.0, "before_runway": 100.0, "pct_of_budget": 50}
    assert certs.budget(rows, None, None)["pct_of_budget"] is None


def test_steps_round_trip_and_bad_json():
    c = db.cert_create({"title": "T"})
    out = db.cert_update(c["id"], {"steps": [{"text": "read", "hours": "1.5"}, {"text": ""}, "junk"]})
    assert out["steps"] == [{"text": "read", "hours": 1.5, "done": False}]
    with db.get_conn() as conn:
        conn.execute("UPDATE certifications SET steps='{{bad', how_to='nope' WHERE id=?", [c["id"]])
    got = db.cert_get(c["id"])
    assert got["steps"] == [] and got["how_to"] is None


def test_api_cannot_write_seed_only_fields():
    c = db.cert_create({"title": "T"})
    out = db.cert_update(c["id"], {"verdict": "CUT", "how_to": {"url": "x"}})
    assert out["verdict"] is None and out["how_to"] is None


def test_certifications_summary_route(monkeypatch):
    import tracker
    client = tracker.app.test_client()
    resp = client.get("/api/certifications/summary")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "budget" in body and "pace" in body


def test_cert_budget_setting_round_trip(tmp_path, monkeypatch):
    from agent import config

    f = tmp_path / "settings.yaml"
    monkeypatch.setattr(config, "SETTINGS_FILE", f)
    monkeypatch.setattr(config, "_CACHE", None)
    assert config.load_settings()["cert_budget"] is None
    config.save_settings({"cert_budget": 800})
    monkeypatch.setattr(config, "_CACHE", None)
    assert config.load_settings()["cert_budget"] == 800
    config.save_settings({"cert_budget": None})
    monkeypatch.setattr(config, "_CACHE", None)
    assert config.load_settings()["cert_budget"] is None


import importlib.util

_spec = importlib.util.spec_from_file_location("seed_cert_research", ROOT / "scripts" / "seed_cert_research.py")
seed_mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(seed_mod)


def _seed_for(ids):
    return {"checked_on": "2026-09-24",
            "verdicts": {i: {"verdict": "CUT", "reason": "r"} for i in ids},
            "keepers": {ids[0]: {"cost_usd": 10, "how_to": {"url": "u", "format": None},
                                 "steps": [{"text": "s1", "hours": 1}]}},
            "new": [{"title": "OSHA 10 (General Industry)", "provider": "p", "track": "phase1",
                     "verdict": "KEEP-NOW", "reason": "r", "cost_usd": 0, "how_to": {"url": "o"},
                     "steps": [{"text": "m1", "hours": 2}]}]}


def test_seed_dry_run_writes_nothing():
    a = db.cert_create({"title": "A"}); b = db.cert_create({"title": "B"})
    seed_mod.run(_seed_for([a["id"], b["id"]]), apply=False)
    assert db.cert_get(a["id"])["verdict"] is None
    assert len(db.certs_all()) == 2


def test_seed_apply_is_idempotent_and_keeps_status():
    a = db.cert_create({"title": "A", "status": "in_progress"}); b = db.cert_create({"title": "B"})
    seed = _seed_for([a["id"], b["id"]])
    seed_mod.run(seed, apply=True)
    seed_mod.run(seed, apply=True)
    got = db.cert_get(a["id"])
    assert got["verdict"] == "CUT" and got["status"] == "in_progress"
    assert got["steps"] == [{"text": "s1", "hours": 1.0, "done": False}]
    assert sum(1 for c in db.certs_all() if c["title"] == "OSHA 10 (General Industry)") == 1


def test_seed_does_not_clobber_ticked_steps():
    a = db.cert_create({"title": "A"}); b = db.cert_create({"title": "B"})
    seed = _seed_for([a["id"], b["id"]])
    seed_mod.run(seed, apply=True)
    db.cert_update(a["id"], {"steps": [{"text": "s1", "hours": 1, "done": True}]})
    seed_mod.run(seed, apply=True)
    assert db.cert_get(a["id"])["steps"][0]["done"] is True


def test_seed_rejects_unknown_ids():
    a = db.cert_create({"title": "A"})
    with pytest.raises(ValueError):
        seed_mod.run(_seed_for([a["id"], "cert_44"]), apply=False)


def test_seed_refreshes_new_row_cost():
    a = db.cert_create({"title": "A"})
    seed = _seed_for([a["id"]])
    seed_mod.run(seed, apply=True)
    seed["new"][0]["cost_usd"] = 42
    seed_mod.run(seed, apply=True)
    row = next(c for c in db.certs_all() if c["title"] == "OSHA 10 (General Industry)")
    assert row["cost_usd"] == 42


# ── later/cut certs must behave like completed/inactive outside the Certs view ──

def test_next_exam_anchor_excludes_cut_and_later():
    soon = (date.today() + timedelta(days=5)).isoformat()
    soonest = (date.today() + timedelta(days=2)).isoformat()
    db.cert_create({"title": "Cut Cert", "status": "cut", "exam_date": soonest})
    db.cert_create({"title": "Later Cert", "status": "later", "exam_date": soonest})
    db.cert_create({"title": "Active Cert", "status": "in_progress", "exam_date": soon})
    a = anchors.plan_anchors()
    assert a["next_exam"] == soon and a["next_exam_title"] == "Active Cert"


def test_timeline_board_excludes_cut_and_later_certs():
    soon = (date.today() + timedelta(days=5)).isoformat()
    cut = db.cert_create({"title": "Cut Cert", "status": "cut", "exam_date": soon})
    later = db.cert_create({"title": "Later Cert", "status": "later", "exam_date": soon})
    db.cert_create({"title": "Active Cert", "status": "in_progress", "exam_date": soon})
    b = timeline_board.board()
    cert_item_ids = {i["source_id"] for i in b["items"] if i["source"] == "cert"}
    assert cut["id"] not in cert_item_ids and later["id"] not in cert_item_ids
    assert f"cert:{cut['id']}" not in {i["id"] for i in b["items"]}


def test_timeline_board_certs_health_ignores_cut_and_later():
    soon = (date.today() + timedelta(days=5)).isoformat()  # <=14d, would count as at-risk if not excluded
    db.cert_create({"title": "Cut Cert", "status": "cut", "exam_date": soon})
    db.cert_create({"title": "Later Cert", "status": "later", "exam_date": soon})
    b = timeline_board.board()
    health = b["health"]["certs"]
    assert health["metrics"]["overdue"] == 0 and health["metrics"]["soon"] == 0
    assert health["status"] == "on_track"


# ── shared Today/Focus cert pick ────────────────────────────────────────────────

def test_next_study_cert_picks_in_progress_soonest_exam_nulls_last():
    a = db.cert_create({"title": "A", "status": "in_progress", "exam_date": None,
                        "steps": [{"text": "s", "hours": 1, "done": False}]})
    b = db.cert_create({"title": "B", "status": "in_progress", "exam_date": "2026-10-01",
                        "steps": [{"text": "s", "hours": 1, "done": False}]})
    db.cert_create({"title": "C (no open steps)", "status": "in_progress",
                    "steps": [{"text": "s", "hours": 1, "done": True}]})
    db.cert_create({"title": "D (wishlist)", "status": "wishlist",
                    "steps": [{"text": "s", "hours": 1, "done": False}]})
    picked = certs.next_study_cert(db.certs_all(), date(2026, 9, 23))
    assert picked["id"] == b["id"]  # dated exam beats a null one
    db.cert_delete(b["id"])
    picked = certs.next_study_cert(db.certs_all(), date(2026, 9, 23))
    assert picked["id"] == a["id"]  # null exam_date sorts last, still picked over none


_NO_GAP_PROFILE = {"profile": {"title": "Test", "certs": []}, "gaps": [], "match_pct": 100, "met": 0, "total": 0}


def test_focus_cert_pick_matches_today_and_links_to_open_id(monkeypatch):
    # Isolate the cert action from the merit-ranked top-6 truncation (skill gaps
    # on a fresh DB otherwise outscore it) — this test is only about the pick.
    monkeypatch.setattr(focus.roadmaps, "gap_analysis", lambda pid: _NO_GAP_PROFILE)
    c = db.cert_create({"title": "In Progress Cert", "status": "in_progress", "exam_date": "2026-10-01",
                        "steps": [{"text": "s", "hours": 1, "done": False}]})
    today = date(2026, 9, 23)
    _, _, link, _, sid = dayplan._fill_cert(today)
    assert sid == c["id"] and link == f"#/certs?open={c['id']}"
    result = focus.compute(today=today)
    cert_action = next(a for a in result["actions"] if a["type"] == "certification")
    assert cert_action["id"] == c["id"]
    assert cert_action["deep_link"] == f"#/certs?open={c['id']}"


def test_focus_wishlist_fallback_skips_cut_verdict(monkeypatch):
    monkeypatch.setattr(focus.roadmaps, "gap_analysis", lambda pid: _NO_GAP_PROFILE)
    cut = db.cert_create({"title": "Cut Wishlist Cert", "status": "wishlist"})
    db.cert_seed_fields(cut["id"], {"verdict": "CUT"})
    keep = db.cert_create({"title": "Keep Wishlist Cert", "status": "wishlist"})
    result = focus.compute(today=date(2026, 9, 23))
    cert_action = next((a for a in result["actions"] if a["type"] == "certification"), None)
    assert cert_action is not None
    assert cert_action["id"] == keep["id"]
