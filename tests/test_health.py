import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import dayplan  # noqa: E402
import health  # noqa: E402

TODAY = date(2026, 9, 15)  # a Tuesday -> pull


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    monkeypatch.setattr(health, "load_settings",
                        lambda: {"weight_goal": None, "weight_start": None, "weight_mode": "cut"})
    yield


def _log(day, **kw):
    return db.health_day_upsert(day.isoformat() if hasattr(day, "isoformat") else day, kw)


def test_workout_library_is_seeded_across_every_split():
    rows = db.workouts_all()
    assert len(rows) == 21
    assert {r["split"] for r in rows} == set(health.SPLITS)
    assert db.workouts_all("pull")[0]["name"] == "Barbell row"


def test_upsert_keeps_one_row_per_day_and_only_writes_given_keys():
    _log(TODAY, weight_lb=171.4)
    row = _log(TODAY, split="pull", minutes=60)
    assert len(db._rows("health_day", "date = ?", (TODAY.isoformat(),))) == 1
    # logging the workout must not wipe the morning's weigh-in
    assert row["weight_lb"] == 171.4
    assert (row["split"], row["minutes"]) == ("pull", 60)


def test_upsert_can_clear_a_value_explicitly():
    _log(TODAY, weight_lb=171.4)
    assert _log(TODAY, weight_lb=None)["weight_lb"] is None


@pytest.mark.parametrize("day,splits", [
    (date(2026, 9, 14), ["push"]),          # Mon
    (date(2026, 9, 15), ["pull"]),          # Tue
    (date(2026, 9, 16), ["legs"]),          # Wed
    (date(2026, 9, 19), ["legs", "zone2"]), # Sat
    (date(2026, 9, 20), ["rest"]),          # Sun
])
def test_gym_goal_follows_the_weekday_split(day, splits):
    g = health.gym_goal(day)
    assert g["splits"] == splits
    assert g["label"] == health.GYM_SPLIT[day.weekday()]
    assert {e["split"] for e in g["exercises"]} == set(splits)


def test_gym_detail_names_real_exercises():
    detail = health.gym_detail(TODAY)
    assert "Barbell row 4x8" in detail
    assert "more" in detail  # 6 pull exercises, only 4 shown


def test_today_gym_block_points_at_the_health_section():
    title, detail, link, kind, _ = dayplan._fill_gym(TODAY)
    assert title == "Gym: Pull (back/bi)"
    assert link == "#/health"
    assert "Barbell row" in detail
    assert kind == "gym"


def test_streak_counts_consecutive_logged_days():
    for d in (date(2026, 9, 13), date(2026, 9, 14), TODAY):
        _log(d, minutes=60)
    assert health.summary(TODAY)["streak_days"] == 3


def test_streak_survives_a_day_logged_yesterday_but_not_today():
    _log(date(2026, 9, 14), minutes=60)
    assert health.summary(TODAY)["streak_days"] == 1


def test_streak_breaks_on_a_gap():
    _log(date(2026, 9, 11), minutes=60)
    _log(TODAY, minutes=60)
    assert health.summary(TODAY)["streak_days"] == 1


def test_sessions_this_week_counts_from_monday_only():
    _log(date(2026, 9, 13), minutes=60)  # previous Sunday
    _log(date(2026, 9, 14), minutes=60)  # Monday
    _log(TODAY, minutes=45)
    s = health.summary(TODAY)
    assert s["sessions_week"] == 2
    assert s["minutes_week"] == 105
    assert s["planned_week"] == health.PLANNED_SESSIONS_PER_WEEK


def test_routine_pct_is_ticks_over_the_seven_day_window():
    _log(TODAY, routine={"sleep": True, "water": True, "steps": True, "protein": False})
    slots = health.ROUTINE_WINDOW_DAYS * len(health.ROUTINE_ITEMS)
    assert health.summary(TODAY)["routine_pct"] == round(3 / slots * 100)


def test_weight_delta_and_average_use_the_two_most_recent_weigh_ins():
    _log(date(2026, 9, 13), weight_lb=176.0)
    _log(date(2026, 9, 14), weight_lb=174.0)
    _log(TODAY, weight_lb=172.0)
    s = health.summary(TODAY)
    assert s["current"] == 172.0
    assert s["delta"] == -2.0
    assert s["avg7"] == 174.0
    assert s["weigh_ins"] == 3


def test_to_goal_is_the_distance_from_the_target(monkeypatch):
    monkeypatch.setattr(health, "load_settings",
                        lambda: {"weight_goal": 160, "weight_start": 180, "weight_mode": "cut"})
    _log(TODAY, weight_lb=172.0)
    s = health.summary(TODAY)
    assert s["to_goal"] == 12.0
    assert s["weight_goal"] == 160


def test_summary_is_safe_with_no_data():
    s = health.summary(TODAY)
    assert s["current"] is None and s["delta"] is None and s["to_goal"] is None
    assert s["streak_days"] == 0 and s["routine_pct"] == 0


def test_payload_carries_everything_the_view_needs():
    p = health.payload(TODAY)
    assert p["today"] == TODAY.isoformat()
    assert {"summary", "gym", "day", "days", "routine_items", "splits"} <= set(p)
    assert len(p["routine_items"]) == len(health.ROUTINE_ITEMS)


# ── settings: the weight goal must be clearable, unlike the sprint anchors ──────

@pytest.fixture
def cfg(tmp_path, monkeypatch):
    import yaml
    import agent.config as c
    f = tmp_path / "settings.yaml"
    f.write_text(yaml.dump({"offer_date": "2026-11-15", "daily_apps": 4}), encoding="utf-8")
    monkeypatch.setattr(c, "SETTINGS_FILE", f)
    monkeypatch.setattr(c, "_CACHE", None)
    return c


def _reload(c):
    c._CACHE = None
    return c.load_settings()


def test_weight_goal_round_trips_and_can_be_cleared(cfg):
    cfg.save_settings({"weight_goal": 160, "weight_start": 180, "weight_mode": "cut"})
    s = _reload(cfg)
    assert (s["weight_goal"], s["weight_start"], s["weight_mode"]) == (160, 180, "cut")

    cfg.save_settings({"weight_goal": None, "weight_start": ""})
    s = _reload(cfg)
    assert s["weight_goal"] is None and s["weight_start"] is None
    assert s["offer_date"] == "2026-11-15"  # unrelated settings survive the clear


def test_none_still_cannot_wipe_a_non_nullable_setting(cfg):
    cfg.save_settings({"offer_date": None, "daily_apps": None})
    s = _reload(cfg)
    assert s["offer_date"] == "2026-11-15"
    assert s["daily_apps"] == 4


def test_profile_link_seed_preserves_notes():
    """Regression: the seed INSERT omitted the `notes` column, so the transcripts
    guidance was silently dropped on every freshly created database."""
    links = {l["key"]: l for l in db.links_all()}
    assert links["transcripts"]["notes"] == (
        "Field is optional (co-op/internship only) on the forms that ask.")
    assert len(links) == 5


# ── calorie target + estimated burn ────────────────────────────────────────────

def _settings(monkeypatch, **over):
    base = {"weight_goal": None, "weight_start": None, "weight_mode": "cut",
            "height_in": 68, "birth_year": 1994, "sex": "male", "daily_delta": 500}
    monkeypatch.setattr(health, "load_settings", lambda: {**base, **over})


def test_bmr_matches_mifflin_st_jeor_by_hand():
    # 172 lb = 78.02 kg, 68 in = 172.72 cm, age 32
    # 10(78.02) + 6.25(172.72) - 5(32) + 5 = 1705
    assert health.bmr(172, 68, 1994, "male", TODAY) == 1705
    assert health.bmr(172, 68, 1994, "female", TODAY) == 1705 - 166  # +5 vs -161


def test_bmr_is_none_until_every_input_is_present():
    assert health.bmr(None, 68, 1994, "male", TODAY) is None
    assert health.bmr(172, None, 1994, "male", TODAY) is None
    assert health.bmr(172, 68, None, "male", TODAY) is None


@pytest.mark.parametrize("split,expected", [("pull", 410), ("push", 410), ("legs", 410),
                                            ("zone2", 573), ("rest", 246)])
def test_session_burn_uses_the_met_for_the_split(split, expected):
    assert health.session_burn(172, split, 60) == expected


def test_session_burn_is_zero_without_weight_or_minutes():
    assert health.session_burn(None, "pull", 60) == 0
    assert health.session_burn(172, "pull", 0) == 0


def test_energy_lists_what_is_missing_and_stays_none(monkeypatch):
    _settings(monkeypatch, height_in=None, sex=None)
    e = health.energy(TODAY)
    assert set(e["missing"]) == {"weight", "height_in", "sex"}
    assert e["bmr"] is None and e["tdee"] is None and e["target"] is None


def test_energy_target_is_tdee_minus_the_deficit_when_cutting(monkeypatch):
    _settings(monkeypatch)
    _log(TODAY, weight_lb=172.0)
    e = health.energy(TODAY)
    assert e["missing"] == []
    assert e["bmr"] == 1705
    assert e["tdee"] == round(1705 * 1.375) == 2344
    assert e["target"] == 2344 - 500


def test_bulk_adds_the_delta_and_maintain_ignores_it(monkeypatch):
    _log(TODAY, weight_lb=172.0)
    _settings(monkeypatch, weight_mode="bulk")
    assert health.energy(TODAY)["target"] == 2344 + 500
    _settings(monkeypatch, weight_mode="maintain")
    assert health.energy(TODAY)["target"] == 2344


def test_daily_delta_is_editable(monkeypatch):
    _log(TODAY, weight_lb=172.0)
    _settings(monkeypatch, daily_delta=250)
    assert health.energy(TODAY)["target"] == 2344 - 250


def test_target_does_not_move_when_a_session_is_skipped(monkeypatch):
    """The flat activity factor is deliberate — burn is measured, target is not."""
    _settings(monkeypatch)
    _log(TODAY, weight_lb=172.0)
    rest = health.energy(TODAY)
    _log(TODAY, split="pull", minutes=60)
    trained = health.energy(TODAY)
    assert rest["target"] == trained["target"]
    assert rest["session_today"] == 0 and trained["session_today"] == 410


def test_burned_today_is_never_zero_once_bmr_is_known(monkeypatch):
    """A rest day still burns BMR + non-exercise activity."""
    _settings(monkeypatch)
    _log(TODAY, weight_lb=172.0)
    rest = health.energy(TODAY)
    assert rest["burn_breakdown"] == {"resting": 1705, "daily": 341, "session": 0}
    assert rest["burned_today"] == 1705 + 341 == 2046
    _log(TODAY, split="pull", minutes=60)
    assert health.energy(TODAY)["burned_today"] == 2046 + 410


def test_burned_week_sums_sessions_from_monday(monkeypatch):
    _settings(monkeypatch)
    _log(TODAY, weight_lb=172.0)
    _log(date(2026, 9, 13), split="pull", minutes=60)  # previous Sunday - excluded
    _log(date(2026, 9, 14), split="legs", minutes=60)  # Monday
    _log(TODAY, split="pull", minutes=60)
    assert health.energy(TODAY)["burned_week"] == 410 * 2


def test_protein_target_scales_with_bodyweight(monkeypatch):
    _settings(monkeypatch)
    _log(TODAY, weight_lb=172.0)
    assert health.energy(TODAY)["protein_g"] == round(172 * health.PROTEIN_G_PER_LB)


# ── target-date projections (both directions) ──────────────────────────────────

GOAL_DAY = date(2026, 10, 15)  # 30 days after TODAY


def test_gain_10_lb_in_30_days_needs_the_surplus_we_quoted():
    p = health.projection(150, 160, GOAL_DAY, "bulk", 1667, 2292, TODAY)
    assert p["days_left"] == 30
    assert p["required_delta"] == 1167          # 10 lb x 3500 / 30
    assert p["required_target"] == 2292 + 1167  # eat 3,459
    assert p["rate_lb_week"] == 2.33


def test_fast_gain_warns_that_it_will_not_all_be_lean():
    p = health.projection(150, 160, GOAL_DAY, "bulk", 1667, 2292, TODAY)
    assert any("lean gain" in w for w in p["warnings"])


def test_slow_gain_inside_the_lean_ceiling_does_not_warn():
    p = health.projection(150, 154, date(2026, 12, 15), "bulk", 1667, 2292, TODAY)
    assert p["warnings"] == []
    assert p["required_delta"] > 0


def test_loss_projection_is_negative_and_warns_below_bmr():
    p = health.projection(150, 140, GOAL_DAY, "cut", 1667, 2292, TODAY)
    assert p["required_delta"] == -1167
    assert p["required_target"] == 1125
    assert any("resting burn" in w for w in p["warnings"])
    assert any("1–2 lb/week" in w for w in p["warnings"])


def test_projection_flags_a_goal_that_contradicts_the_mode():
    p = health.projection(150, 140, GOAL_DAY, "bulk", 1667, 2292, TODAY)
    assert any("bulk but the goal is below" in w for w in p["warnings"])


def test_projection_rejects_a_date_in_the_past():
    p = health.projection(150, 160, date(2026, 9, 1), "bulk", 1667, 2292, TODAY)
    assert p["required_delta"] is None
    assert any("past" in w for w in p["warnings"])


def test_projection_is_empty_without_a_goal_or_a_date():
    assert health.projection(150, None, GOAL_DAY, "bulk", 1667, 2292, TODAY)["required_delta"] is None
    assert health.projection(150, 160, None, "bulk", 1667, 2292, TODAY)["required_delta"] is None


def test_goal_date_overrides_the_typed_daily_delta(monkeypatch):
    _settings(monkeypatch, weight_mode="bulk", weight_goal=160, daily_delta=250,
              goal_date=GOAL_DAY.isoformat())
    _log(TODAY, weight_lb=150.0)
    e = health.energy(TODAY)
    assert e["projection"]["required_delta"] == e["daily_delta"]  # derived, not the typed 250
    assert e["target"] == e["projection"]["required_target"]
