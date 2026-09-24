"""Route smoke test (every GET route answers 200 on a fresh and on a demo database)
and the localhost Host/Origin guard."""
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import news  # noqa: E402
import tracker  # noqa: E402

# Parameterised GET routes: a value that exists in every install.
SAMPLE_ARGS = {"rid": "robotics-controls", "track": "controls"}
# GET routes whose job is to 404 on missing input (no job-run folder / no such file).
EXPECT_404 = {"/api/jobs/runs/<date>", "/api/jobs/file/<date>/<slug>/<which>"}
# GET routes that require a query string.
QUERY = {"/api/skills/gap-analysis": "?profile=controls-engineer", "/api/focus": "?profile=controls-engineer"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    monkeypatch.setattr(news, "_fetch", lambda topic: [])  # no network in tests
    tracker.app.config.update(TESTING=True, ASCENT_PORTS={5001})
    yield tracker.app.test_client()
    tracker.app.config.pop("ASCENT_PORTS", None)


def _get_rules():
    for rule in tracker.app.url_map.iter_rules():
        if "GET" in rule.methods and rule.endpoint != "static":
            yield rule


def _url(rule):
    url = rule.rule
    for arg in rule.arguments:
        url = url.replace(f"<{arg}>", SAMPLE_ARGS.get(arg, "x"))
    return url + QUERY.get(rule.rule, "")


def _seed_demo(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import seed_demo
    seed_demo.seed(tmp_path, date.today())


@pytest.mark.parametrize("data", ["fresh", "demo"])
def test_every_get_route_answers(client, tmp_path, data):
    if data == "demo":
        _seed_demo(tmp_path)
    checked = 0
    for rule in _get_rules():
        if rule.rule == "/":
            continue  # needs the built frontend; covered by the fresh-clone check
        r = client.get(_url(rule))
        want = 404 if rule.rule in EXPECT_404 else 200
        assert r.status_code == want, f"{rule.rule} -> {r.status_code}: {r.get_data(as_text=True)[:200]}"
        checked += 1
    assert checked >= 45


def test_fresh_install_modules_are_off(client):
    assert client.get("/api/modules").get_json() == {"side": False, "clips": False, "health": False}
    cats = client.get("/api/day").get_json()["cats"]
    assert not {"clips", "gym", "bridge"} & set(cats)


def test_instance_reports_the_served_database(client, tmp_path):
    assert Path(client.get("/api/instance").get_json()["db"]) == (tmp_path / "t.db").resolve()


# ── localhost guard ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("host", ["localhost", "127.0.0.1:5001", "localhost:5001", "[::1]:5001", "localhost:5173"])
def test_loopback_hosts_pass(client, host):
    assert client.get("/api/modules", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["attacker.example", "attacker.example:5001", "127.0.0.1.nip.io:5001",
                                  "192.168.1.20:5001", "127.0.0.1:8080", "localhost.attacker.example"])
def test_rebinding_hosts_are_rejected(client, host):
    r = client.get("/api/linda/context", headers={"Host": host})
    assert r.status_code == 403 and r.get_json()["error"] == "forbidden host"


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5001", "http://localhost:5173"])
def test_same_app_origins_can_post(client, origin):
    r = client.post("/api/reminders/sync", headers={"Origin": origin})
    assert r.status_code == 200


@pytest.mark.parametrize("origin", ["https://attacker.example", "http://127.0.0.1:9999", "null",
                                    "http://localhost.attacker.example"])
def test_cross_site_origins_are_rejected(client, origin):
    r = client.post("/api/projects/export", data="x", content_type="text/plain", headers={"Origin": origin})
    assert r.status_code == 403 and r.get_json()["error"] == "forbidden origin"


def test_cross_site_post_without_origin_is_rejected(client):
    r = client.post("/api/reminders/sync", data="x", content_type="text/plain",
                    headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_guard_allows_any_loopback_port_when_no_port_is_configured(client):
    tracker.app.config.pop("ASCENT_PORTS")
    assert client.get("/api/modules", headers={"Host": "127.0.0.1:4321"}).status_code == 200
    assert client.get("/api/modules", headers={"Host": "attacker.example:4321"}).status_code == 403


def test_servers_bind_loopback_only():
    for src in ("app.py", "tracker.py"):
        text = (ROOT / src).read_text(encoding="utf-8")
        assert 'host="127.0.0.1"' in text and "0.0.0.0" not in text
