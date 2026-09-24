"""The perf pass added mtime-keyed parse caches. These assert they actually
invalidate — a stale settings.yaml or schedule.yaml would silently freeze the
Today template and every anchor date."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import dayplan  # noqa: E402
import yamlio  # noqa: E402
from agent import config  # noqa: E402


def _touch_write(path: Path, text: str):
    path.write_text(text, encoding="utf-8")
    # mtime resolution: make sure the stat actually differs from the last write
    time.sleep(0.01)


def test_yamlio_matches_safe_load():
    import yaml
    text = "a: 1\nb:\n  - x\n  - y\ntimes:\n  start: '08:30'\n"
    assert yamlio.load(text) == yaml.safe_load(text)


def test_load_settings_reloads_when_file_changes(tmp_path, monkeypatch):
    f = tmp_path / "settings.yaml"
    _touch_write(f, "daily_apps: 4\n")
    monkeypatch.setattr(config, "SETTINGS_FILE", f)
    monkeypatch.setattr(config, "_CACHE", None)
    assert config.load_settings()["daily_apps"] == 4
    _touch_write(f, "daily_apps: 9\n")
    assert config.load_settings()["daily_apps"] == 9


def test_load_schedule_reloads_when_file_changes(tmp_path, monkeypatch):
    f = tmp_path / "schedule.yaml"
    _touch_write(f, 'wake: "07:00"\nhard_stop: "22:00"\ntemplates:\n  weekday:\n  - start: "08:30"\n    min: 60\n    cat: apps\n')
    monkeypatch.setattr(dayplan, "SCHEDULE_FILE", f)
    monkeypatch.setattr(dayplan, "_SCHED_CACHE", None)
    assert dayplan.load_schedule()["wake"] == "07:00"
    _touch_write(f, 'wake: "06:15"\nhard_stop: "22:00"\ntemplates:\n  weekday: []\n')
    assert dayplan.load_schedule()["wake"] == "06:15"


def test_load_schedule_keeps_times_as_strings(tmp_path, monkeypatch):
    """08:30 unquoted is sexagesimal in YAML 1.1 — the round trip must not
    turn block starts into integers."""
    f = tmp_path / "schedule.yaml"
    _touch_write(f, 'wake: "07:00"\nhard_stop: "22:00"\ntemplates:\n  weekday:\n  - start: "08:30"\n    min: 120\n    cat: apps\n')
    monkeypatch.setattr(dayplan, "SCHEDULE_FILE", f)
    monkeypatch.setattr(dayplan, "_SCHED_CACHE", None)
    assert dayplan.load_schedule()["templates"]["weekday"][0]["start"] == "08:30"
