import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import offer_analyzer, prompts  # noqa: E402
from agent import profile as prof  # noqa: E402


@pytest.fixture
def no_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(prof, "PROFILE_FILE", tmp_path / "missing.yaml")


@pytest.fixture
def jordan(tmp_path, monkeypatch):
    f = tmp_path / "profile.yaml"
    f.write_text("name: Jordan Rivera\nmarket: Denver, CO\ncurrent_salary: 80000\n"
                 "target_salary: 100000\nmonthly_expenses: 3000\nabout: '## Jordan'\n", encoding="utf-8")
    monkeypatch.setattr(prof, "PROFILE_FILE", f)


def test_missing_profile_falls_back_to_neutral_defaults(no_profile):
    p = prof.load_profile()
    assert p["name"] == "" and p["current_salary"] is None and p["achievements"] == []
    assert prof.first_name() == "" and prof.file_prefix() == "Candidate"


def test_prompt_without_profile_names_nobody(no_profile):
    s = prompts.build_system_prompt()
    assert "co-pilot for the user" in s and "No profile is configured" in s


def test_prompt_uses_profile_name_market_and_about(jordan):
    s = prompts.build_system_prompt()
    assert "co-pilot for Jordan Rivera" in s and "Jordan's dedicated" in s
    assert "paying in Denver, CO" in s and "## Jordan" in s
    assert prof.file_prefix() == "JordanRivera"


def test_offer_without_baseline_reports_none_instead_of_guessing(no_profile):
    r = offer_analyzer.analyze_offer({"base": 90000})
    assert r["offer_summary"]["raise_pct"] is None and r["walk_away_threshold"] is None
    assert r["take_home"]["monthly_savings"] is None and r["verdict"] == "NEGOTIATE"


def test_offer_uses_profile_baseline(jordan):
    r = offer_analyzer.analyze_offer({"base": 100000})
    assert r["offer_summary"]["raise_pct"] == 25.0 and r["verdict"] == "ACCEPT"
    assert r["take_home"]["monthly_savings"] == r["take_home"]["monthly"] - 3000


def test_env_overrides_point_db_settings_and_profile_elsewhere(tmp_path, monkeypatch):
    monkeypatch.setenv("ASCENT_DB", str(tmp_path / "demo.db"))
    monkeypatch.setenv("ASCENT_SETTINGS", str(tmp_path / "settings.yaml"))
    monkeypatch.setenv("ASCENT_PROFILE", str(tmp_path / "profile.yaml"))
    import db
    from agent import config
    try:
        assert importlib.reload(db).DB_PATH == tmp_path / "demo.db"
        assert importlib.reload(config).SETTINGS_FILE == tmp_path / "settings.yaml"
        assert importlib.reload(prof).PROFILE_FILE == tmp_path / "profile.yaml"
    finally:
        monkeypatch.undo()
        importlib.reload(db), importlib.reload(config), importlib.reload(prof)
