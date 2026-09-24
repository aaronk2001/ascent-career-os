import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import projects  # noqa: E402


# (slug, name, tier, path) - a small inventory; a fresh install seeds none.
FIXTURE = [
    ("edge-defect", "Edge defect detection", "core", "robots/edge-defect"),
    ("arm", "Robot arm", "core", "robots/arm"),
    ("sorter", "Sorter cell", "core", "plc/sorter"),
    ("tts", "TTS app", "other", "apps/tts"),
    ("old-bot", "Old bot", "other", "robots/old-bot"),
]
N_CORE, N_OTHER = 3, 2


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    for i, (slug, name, tier, path) in enumerate(FIXTURE):
        db.project_add({"slug": slug, "name": name, "tier": tier, "path": path, "sort": i})
    yield


def test_fresh_install_seeds_no_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "fresh.db")
    db.init_db()
    assert db.projects_all() == []
    assert projects.all_grouped()["overall"] == {"percent": 0, "complete_count": 0, "shipped_count": 0, "total": 0}


def test_init_db_never_touches_existing_projects():
    before = db.projects_all()
    db.project_update(before[0]["id"], {"problem": "mine"})
    db.init_db()
    after = db.projects_all()
    assert len(after) == len(before) and after[0]["problem"] == "mine"


def test_add_update_delete_round_trip():
    row = db.project_add({"name": "Test Rig", "slug": "test-rig", "tier": "other"})
    assert row["id"].startswith("proj_")
    assert db.project_update(row["id"], {"pitch": "thirty seconds"})["pitch"] == "thirty seconds"
    assert db.project_delete(row["id"]) is True
    assert db.project_get(row["id"]) is None


def _blank():
    return {"problem": "", "built": None, "result": "", "pitch": ""}


def test_completeness_uses_three_fields_and_ignores_pitch():
    assert projects.completeness(_blank()) == 0
    assert projects.completeness({**_blank(), "problem": "x"}) == 33
    assert projects.completeness({**_blank(), "problem": "x", "built": "y", "result": "z"}) == 100
    assert projects.completeness({**_blank(), "pitch": "only pitch"}) == 0
    # dropped fields no longer count
    assert projects.completeness({**_blank(), "decision": "d", "differently": "e"}) == 0


def test_ship_state_normalizes_and_survives_bad_json():
    assert projects.ship_state({"ship": None}) == {k: False for k, _ in projects.SHIP_ITEMS}
    assert projects.ship_state({"ship": "not json"}) == {k: False for k, _ in projects.SHIP_ITEMS}
    s = projects.ship_state({"ship": '{"repo": true, "junk": true, "demo": 1}'})
    assert s == {"repo": True, "readme": False, "demo": True, "bullet": False, "portfolio": False}


def test_ship_round_trip_through_update():
    row = db.projects_all()[0]
    out = db.project_update(row["id"], {"ship": {"repo": True, "extra": True}})
    d = projects.decorate(out)
    assert d["ship"]["repo"] is True and "extra" not in d["ship"]
    assert d["ship_done"] == 1
    import json
    assert json.loads(out["ship"]) == {"repo": True, "readme": False, "demo": False,
                                       "bullet": False, "portfolio": False}


def test_ship_non_dict_is_dropped_not_500():
    row = db.projects_all()[0]
    before = row.get("ship")
    out = db.project_update(row["id"], {"ship": "not a dict", "problem": "still applied"})
    assert out["ship"] == before
    assert out["problem"] == "still applied"


def test_overall_counts_fully_shipped_core():
    core = [r for r in db.projects_all() if r["tier"] == "core"]
    db.project_update(core[0]["id"], {"ship": {k: True for k, _ in projects.SHIP_ITEMS}})
    o = projects.all_grouped()["overall"]
    assert o["shipped_count"] == 1 and o["total"] == len(core)


def test_export_has_three_story_headings_only():
    md = projects.render_markdown()
    assert "### Problem" in md and "### Result & numbers" in md
    assert "Hardest decision" not in md and "What I'd do differently" not in md


def test_whitespace_only_counts_as_blank():
    assert projects.completeness({**_blank(), "result": "   \n  "}) == 0


def test_overall_counts_core_completion():
    rows = [{**_blank(), "tier": "core"},
            {**{f: "x" for f in projects.STORY_FIELDS}, "tier": "core"},
            {**{f: "x" for f in projects.STORY_FIELDS}, "tier": "other"}]
    out = projects.overall(rows)
    assert out == {"percent": 50, "complete_count": 1, "total": 2, "shipped_count": 0}


def test_all_grouped_splits_tiers_and_decorates():
    out = projects.all_grouped()
    assert len(out["core"]) == N_CORE and len(out["other"]) == N_OTHER
    assert all("completeness" in r for r in out["core"] + out["other"])
    assert out["overall"]["percent"] == 0
    assert out["overall"]["total"] == N_CORE


def test_set_tier_promotes_and_survives_a_reload():
    other = projects.all_grouped()["other"][0]
    promoted = projects.set_tier(other["id"], "core")
    assert promoted["tier"] == "core"
    assert any(r["id"] == other["id"] for r in projects.all_grouped()["core"])


def test_set_tier_rejects_unknown_id():
    assert projects.set_tier("proj_nope", "core") is None


def test_render_lists_every_project_in_the_index():
    md = projects.render_markdown()
    for r in db.projects_all():
        assert r["name"] in md


def test_render_marks_unfilled_blanks():
    md = projects.render_markdown()
    assert md.count("_(blank)_") == N_CORE * len(projects.STORY_FIELDS)


def test_render_only_sections_core_projects():
    g = projects.all_grouped()
    md = projects.render_markdown()
    # len(core) project sections, plus the one "## Index" heading.
    assert md.count("\n## ") == len(g["core"]) + 1
    for r in g["core"]:
        assert f"\n## {r['name']}\n" in md
    for r in g["other"]:
        assert f"\n## {r['name']}\n" not in md


def test_render_includes_written_answers():
    row = projects.all_grouped()["core"][0]
    db.project_update(row["id"], {"pitch": "A fleet of 180 robots, one control plane."})
    md = projects.render_markdown()
    assert "A fleet of 180 robots, one control plane." in md
    assert md.count("_(blank)_") == N_CORE * len(projects.STORY_FIELDS)


def test_export_writes_the_file(tmp_path, monkeypatch):
    target = tmp_path / "PROJECTS.md"
    monkeypatch.setattr(projects, "PROJECTS_MD", target)
    out = projects.export_markdown()
    assert out == str(target)
    assert "# Projects" in target.read_text(encoding="utf-8")


@pytest.fixture
def client(tmp_db):
    import tracker
    tracker.app.config["TESTING"] = True
    return tracker.app.test_client()


def test_get_returns_grouped_payload(client):
    body = client.get("/api/projects").get_json()
    assert set(body) == {"core", "other", "overall"}
    assert len(body["core"]) == N_CORE


def test_post_requires_a_name(client):
    assert client.post("/api/projects", json={}).status_code == 400
    assert client.post("/api/projects", json={"name": "  "}).status_code == 400


def test_post_creates_a_project(client):
    body = client.post("/api/projects", json={"name": "New Rig", "tier": "other"}).get_json()
    assert body["name"] == "New Rig"
    assert body["completeness"] == 0


def test_put_updates_and_recomputes_completeness(client):
    pid = client.get("/api/projects").get_json()["core"][0]["id"]
    body = client.put(f"/api/projects/{pid}", json={"problem": "flaky fleet"}).get_json()
    assert body["completeness"] == 33


def test_put_unknown_id_is_404(client):
    assert client.put("/api/projects/proj_nope", json={"pitch": "x"}).status_code == 404


def test_tier_route_validates(client):
    pid = client.get("/api/projects").get_json()["other"][0]["id"]
    assert client.put(f"/api/projects/{pid}/tier", json={"tier": "bogus"}).status_code == 400
    assert client.put(f"/api/projects/{pid}/tier", json={"tier": "core"}).get_json()["tier"] == "core"


def test_delete_then_404(client):
    pid = client.post("/api/projects", json={"name": "Temp"}).get_json()["id"]
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.delete(f"/api/projects/{pid}").status_code == 404


def test_export_route_writes_the_file(client, tmp_path, monkeypatch):
    target = tmp_path / "PROJECTS.md"
    monkeypatch.setattr(projects, "PROJECTS_MD", target)
    body = client.post("/api/projects/export").get_json()
    assert body["ok"] is True
    assert target.exists()


def _core(slug="edge-defect"):
    return next(r for r in db.projects_all() if r["slug"] == slug)


def test_draft_422_when_no_source_file(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_ROOT", tmp_path)
    with pytest.raises(projects.DraftError) as e:
        projects.draft(_core()["id"])
    assert e.value.status == 422 and "robots/edge-defect" in e.value.message


def test_draft_503_when_ollama_down(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_ROOT", tmp_path)
    d = tmp_path / "robots" / "edge-defect"
    d.mkdir(parents=True)
    (d / "README.md").write_text("# Edge\nYOLO on a Pi", encoding="utf-8")

    def boom(*a, **k):
        raise ConnectionError("connection refused")
    monkeypatch.setattr(projects, "_chat_json", boom)
    with pytest.raises(projects.DraftError) as e:
        projects.draft(_core()["id"])
    assert e.value.status == 503


def test_draft_returns_four_strings_and_caps_input(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "PROJECTS_ROOT", tmp_path)
    d = tmp_path / "robots" / "edge-defect"
    d.mkdir(parents=True)
    (d / "README.md").write_text("x" * 20000, encoding="utf-8")
    seen = {}

    def fake(system, user, model=None):
        seen["len"] = len(user)
        return {"problem": "p", "built": "b", "result": "r", "bullet": "• did 3x", "extra": 1}, "m", False
    monkeypatch.setattr(projects, "_chat_json", fake)
    out = projects.draft(_core()["id"])
    assert out == {"problem": "p", "built": "b", "result": "r", "bullet": "• did 3x"}
    assert seen["len"] < 6000 + 1000  # 6000-char source cap + prompt framing


def test_draft_404_unknown_project():
    with pytest.raises(projects.DraftError) as e:
        projects.draft("proj_nope")
    assert e.value.status == 404


def test_draft_route_404_unknown_project(client):
    resp = client.post("/api/projects/proj_nope/draft")
    assert resp.status_code == 404
    assert resp.get_json()["ok"] is False


def test_draft_422_when_path_blank_even_if_root_has_readme(tmp_path, monkeypatch):
    # PROJECTS_ROOT itself has a README.md — proves a blank path is rejected
    # up front rather than falling through to Path("") resolving to the root.
    (tmp_path / "README.md").write_text("# Not this project", encoding="utf-8")
    monkeypatch.setattr(projects, "PROJECTS_ROOT", tmp_path)
    row = db.project_add({"name": "No Path", "slug": "no-path"})
    with pytest.raises(projects.DraftError) as e:
        projects.draft(row["id"])
    assert e.value.status == 422 and "(no path set)" in e.value.message


@pytest.mark.parametrize("path", ["../outside", "robots/../../outside", "/etc", "C:/Windows"])
def test_draft_refuses_paths_outside_the_projects_root(tmp_path, monkeypatch, path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "README.md").write_text("# secret", encoding="utf-8")
    monkeypatch.setattr(projects, "PROJECTS_ROOT", root)
    row = db.project_add({"name": "Escape", "slug": "escape", "path": path})
    with pytest.raises(projects.DraftError) as e:
        projects.draft(row["id"])
    assert e.value.status in (403, 422)
    assert "secret" not in e.value.message


def test_projects_md_defaults_next_to_the_database_not_outside_the_repo():
    assert projects.PROJECTS_ROOT.resolve() == Path(os.environ["ASCENT_PROJECTS_ROOT"]).resolve()
    assert projects.PROJECTS_MD.name == "PROJECTS.md"
    assert projects.PROJECTS_MD.parent.resolve() == projects.PROJECTS_ROOT.resolve()
