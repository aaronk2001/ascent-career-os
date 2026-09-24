"""Personal health — weight goal, workout log, daily routine.

One row per day in `health_day`; the workout library lives in `workouts` and is
editable from the Health section. dayplan imports this module (never the other
way round) so the Today gym goal and the Health page read the same workout.
"""
from datetime import date, timedelta

import db
from agent.config import load_settings

# Which split each weekday gets. Owned here rather than in dayplan so the Today
# goal and the Health page cannot drift apart.
GYM_SPLIT = {0: "Push (chest/shoulders/tri)", 1: "Pull (back/bi)", 2: "Legs", 3: "Push", 4: "Pull",
             5: "Legs + 20 min zone-2", 6: "Rest / walk"}
# weekday -> the workout-library splits that make up that day
SPLIT_KEYS = {0: ("push",), 1: ("pull",), 2: ("legs",), 3: ("push",), 4: ("pull",),
              5: ("legs", "zone2"), 6: ("rest",)}
SPLITS = ("push", "pull", "legs", "zone2", "rest")

ROUTINE_ITEMS = [
    {"key": "sleep", "label": "7+ hours sleep"},
    {"key": "daylight", "label": "10 min daylight before noon"},
    {"key": "water", "label": "100 oz water"},
    {"key": "protein", "label": "Protein target hit"},
    {"key": "steps", "label": "8,000 steps"},
    {"key": "screens", "label": "Screens off by 22:00"},
]
# schedule.yaml plans a gym block on all five weekdays plus Saturday
PLANNED_SESSIONS_PER_WEEK = 6
ROUTINE_WINDOW_DAYS = 7

LB_TO_KG = 0.45359237
IN_TO_CM = 2.54
# "lightly active" — gym plus small daily activity. Deliberately a FLAT factor:
# the target does not move when a session is skipped, so a rest day carries
# roughly 400 kcal of activity that did not happen. Burn below is display-only.
ACTIVITY_FACTOR = 1.375
# Compendium of Physical Activities MET values, per workout split
MET = {"push": 5.0, "pull": 5.0, "legs": 5.0, "zone2": 7.0, "rest": 3.0}
DEFAULT_MET = 5.0
PROTEIN_G_PER_LB = 0.9
KCAL_PER_LB = 3500
# Non-exercise baseline. burned_today = BMR + NEAT + the logged session, so a
# rest day still reports real expenditure instead of 0.
NEAT_FACTOR = 1.2
# Rate ceilings used only to warn, never to clamp — the user stays in control.
LEAN_GAIN_LB_WEEK = 1.0
SAFE_LOSS_LB_WEEK = 2.0


def bmr(weight_lb, height_in, birth_year, sex, today=None):
    """Mifflin-St Jeor resting burn, or None if any input is missing."""
    if not (weight_lb and height_in and birth_year):
        return None
    today = today or date.today()
    age = today.year - int(birth_year)
    base = 10 * weight_lb * LB_TO_KG + 6.25 * height_in * IN_TO_CM - 5 * age
    return round(base + (5 if str(sex).lower() == "male" else -161))


def session_burn(weight_lb, split, minutes):
    """MET x kg x hours x 1.05 — the standard Compendium estimate."""
    if not weight_lb or not minutes:
        return 0
    return round(MET.get(split or "", DEFAULT_MET) * weight_lb * LB_TO_KG * (minutes / 60) * 1.05)


def projection(current, goal_w, goal_date, mode, resting, tdee, today):
    """Daily delta required to reach `goal_w` by `goal_date`, plus warnings.
    3500 kcal/lb is a linear rule — it overstates long-run loss because BMR
    falls as you get lighter, so treat it as a planning number."""
    out = {"goal_date": goal_date.isoformat() if goal_date else None, "days_left": None,
           "required_delta": None, "required_target": None, "rate_lb_week": None, "warnings": []}
    if not (current and goal_w and goal_date):
        return out
    days = (goal_date - today).days
    out["days_left"] = days
    if days <= 0:
        out["warnings"].append("Target date is today or in the past — pick a later one.")
        return out
    lbs = float(goal_w) - current                      # positive = gain
    if abs(lbs) < 0.1:
        out["warnings"].append("Already at the goal weight.")
        return out
    if mode == "bulk" and lbs < 0:
        out["warnings"].append("Mode is bulk but the goal is below your current weight.")
    if mode == "cut" and lbs > 0:
        out["warnings"].append("Mode is cut but the goal is above your current weight.")
    delta = round(lbs * KCAL_PER_LB / days)
    rate = round(abs(lbs) / (days / 7), 2)
    out.update({"required_delta": delta, "required_target": tdee + delta if tdee else None,
                "rate_lb_week": rate})
    if lbs > 0 and rate > LEAN_GAIN_LB_WEEK:
        out["warnings"].append(
            f"{rate} lb/week is above the ~{LEAN_GAIN_LB_WEEK} lb/week ceiling for mostly-lean gain "
            f"— expect a good share of it to be fat and water.")
    if lbs < 0 and rate > SAFE_LOSS_LB_WEEK:
        out["warnings"].append(f"{rate} lb/week is above the usual 1–2 lb/week band.")
    if resting and tdee and tdee + delta < resting:
        out["warnings"].append(f"Eating {tdee + delta} is below your resting burn of {resting}.")
    return out


def energy(today=None, days=None):
    """Calorie target from BMR x activity factor, signed by weight_mode, plus the
    burn actually logged. `missing` lists the inputs the formula still needs."""
    today = today or date.today()
    days = db.health_days() if days is None else days
    s = load_settings()
    iso = today.isoformat()
    current = next((d["weight_lb"] for d in days if d.get("weight_lb")), None)
    row = next((d for d in days if d["date"] == iso), None) or {}
    week_start = (today - timedelta(days=today.weekday())).isoformat()

    mode = s.get("weight_mode") or "cut"
    delta = int(s.get("daily_delta") or 0)
    out = {
        "missing": [k for k, v in (("weight", current), ("height_in", s.get("height_in")),
                                   ("birth_year", s.get("birth_year")), ("sex", s.get("sex"))) if not v],
        "bmr": None, "tdee": None, "target": None,
        "activity_factor": ACTIVITY_FACTOR, "mode": mode, "daily_delta": delta,
        "session_today": session_burn(current, row.get("split"), row.get("minutes") or 0),
        "burned_today": None, "burn_breakdown": None,
        "burned_week": sum(session_burn(current, d.get("split"), d.get("minutes") or 0)
                           for d in days if week_start <= d["date"] <= iso),
        "protein_g": round(current * PROTEIN_G_PER_LB) if current else None,
        "height_in": s.get("height_in"), "birth_year": s.get("birth_year"), "sex": s.get("sex"),
    }
    if out["missing"]:
        out["projection"] = projection(current, s.get("weight_goal"), _d(s.get("goal_date")),
                                       mode, None, None, today)
        return out
    b = bmr(current, s["height_in"], s["birth_year"], s["sex"], today)
    tdee = round(b * ACTIVITY_FACTOR)
    neat = round(b * (NEAT_FACTOR - 1))
    session = out["session_today"]
    out.update({
        "bmr": b, "tdee": tdee,
        "burned_today": b + neat + session,
        "burn_breakdown": {"resting": b, "daily": neat, "session": session},
        "target": tdee - delta if mode == "cut" else tdee + delta if mode == "bulk" else tdee,
    })
    proj = projection(current, s.get("weight_goal"), _d(s.get("goal_date")), mode, b, tdee, today)
    out["projection"] = proj
    # a target date, when set, is what drives the delta
    if proj.get("required_target"):
        out["target"] = proj["required_target"]
        out["daily_delta"] = abs(proj["required_delta"])
    return out


def _d(v):
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def goal():
    s = load_settings()
    return {"weight_goal": s.get("weight_goal"), "weight_start": s.get("weight_start"),
            "weight_mode": s.get("weight_mode"), "goal_date": s.get("goal_date")}


def gym_goal(day=None):
    """Today's split and its exercises — the Today gym goal and the Health page."""
    day = day or date.today()
    wd = day.weekday()
    return {"weekday": wd, "label": GYM_SPLIT[wd], "splits": list(SPLIT_KEYS[wd]),
            "exercises": [w for key in SPLIT_KEYS[wd] for w in db.workouts_all(key)]}


def gym_detail(day=None, limit=4):
    """One-line exercise summary for the Today block detail."""
    ex = gym_goal(day)["exercises"]
    if not ex:
        return "No exercises in the library for this split yet — add some in Health."
    head = " · ".join(f"{e['name']} {e['sets']}".strip() for e in ex[:limit])
    return head + (f" · +{len(ex) - limit} more" if len(ex) > limit else "")


def _streak(trained, today):
    """Consecutive days with a logged session, ending today or yesterday."""
    n, cur = 0, today
    if cur.isoformat() not in trained:
        cur -= timedelta(days=1)
    while cur.isoformat() in trained:
        n += 1
        cur -= timedelta(days=1)
    return n


def summary(today=None, days=None):
    today = today or date.today()
    days = db.health_days() if days is None else days  # newest first
    weights = [(d["date"], d["weight_lb"]) for d in days if d.get("weight_lb")]
    current = weights[0][1] if weights else None
    prev = weights[1][1] if len(weights) > 1 else None
    recent = [w for _, w in weights[:7]]

    g = goal()
    target = g.get("weight_goal")
    to_goal = round(current - float(target), 1) if (current is not None and target) else None

    trained = {d["date"] for d in days if (d.get("minutes") or 0) > 0}
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    in_week = [d for d in days if week_start <= d["date"] <= today.isoformat()]

    span = [(today - timedelta(days=i)).isoformat() for i in range(ROUTINE_WINDOW_DAYS)]
    by_date = {d["date"]: d for d in days}
    ticked = sum(1 for x in span for v in (by_date.get(x, {}).get("routine") or {}).values() if v)
    slots = len(span) * len(ROUTINE_ITEMS)

    return {
        "current": current,
        "delta": round(current - prev, 1) if (current is not None and prev is not None) else None,
        "avg7": round(sum(recent) / len(recent), 1) if recent else None,
        "to_goal": to_goal,
        "weigh_ins": len(weights),
        "streak_days": _streak(trained, today),
        "sessions_week": sum(1 for d in in_week if (d.get("minutes") or 0) > 0),
        "planned_week": PLANNED_SESSIONS_PER_WEEK,
        "minutes_week": sum(d.get("minutes") or 0 for d in in_week),
        "routine_pct": round(ticked / slots * 100) if slots else 0,
        **g,
    }


def payload(today=None):
    today = today or date.today()
    days = db.health_days()  # one scan feeds the summary, today's row and the trend
    iso = today.isoformat()
    return {"today": iso, "summary": summary(today, days), "gym": gym_goal(today),
            "energy": energy(today, days),
            "day": next((d for d in days if d["date"] == iso), None), "days": days[:60],
            "routine_items": ROUTINE_ITEMS, "splits": list(SPLITS),
            "gym_split": {str(k): v for k, v in GYM_SPLIT.items()}}
