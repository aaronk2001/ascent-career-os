"""
Offer analysis agent — evaluates job offers vs the saved profile baseline.
Baseline numbers (current salary, expenses, net worth, targets) come from
profile.yaml; any that are missing are reported as None instead of guessed.
"""
from .profile import load_profile

STATE_TAX_ESTIMATE = 0.025
FEDERAL_TAX_ESTIMATE = 0.22


def analyze_offer(offer: dict) -> dict:
    """
    Analyze a job offer.
    offer = {base, bonus, equity_value, pto_days, remote_days, location, benefits_value}
    """
    p = load_profile()
    current = p["current_salary"]
    target = p["target_salary"]
    expenses = p["monthly_expenses"]
    net_worth = p["net_worth"]

    base = offer.get("base", 0)
    bonus = offer.get("bonus", 0)
    equity = offer.get("equity_value", 0)
    total_comp = base + bonus + equity / 4

    raise_pct = round((base - current) / current * 100, 1) if current else None

    monthly_take_home = round(base * (1 - STATE_TAX_ESTIMATE - FEDERAL_TAX_ESTIMATE) / 12)
    monthly_savings = monthly_take_home - expenses if expenses is not None else None
    annual_savings = monthly_savings * 12 if monthly_savings is not None else None
    nw_1yr = net_worth + annual_savings if net_worth is not None and annual_savings is not None else None

    walk_away = current * 1.15 if current else None
    target_counter = round(base * 1.08 / 1000) * 1000

    if target and base >= target:
        verdict = "ACCEPT"
    elif walk_away is None or base >= walk_away:
        verdict = "NEGOTIATE"
    else:
        verdict = "DECLINE"

    return {
        "offer_summary": {
            "base": base,
            "total_comp_estimate": round(total_comp),
            "raise_pct": raise_pct,
            "vs_target": base >= target if target else None,
        },
        "take_home": {
            "monthly": monthly_take_home,
            "monthly_savings": monthly_savings,
            "annual_savings": annual_savings,
        },
        "fire_trajectory": {
            "nw_in_1yr": nw_1yr,
            "on_track": (nw_1yr >= p["target_net_worth_1yr"]
                         if nw_1yr is not None and p["target_net_worth_1yr"] else None),
        },
        "verdict": verdict,
        "walk_away_threshold": walk_away,
        "counter_offer": target_counter,
        "negotiation_script": (
            f"I'm very excited about this role. Based on my research and the scope of responsibility, "
            f"I was targeting ${target_counter:,}. Is there flexibility to get there? "
            f"I'm also open to discussing signing bonus or additional equity if base has constraints."
        ),
    }
