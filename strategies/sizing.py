from __future__ import annotations

import math

import pandas as pd

from strategies.scoring import conviction_tier


def target_position_dollars(row: pd.Series, portfolio_value: float, settings: dict) -> float:
    sizing = settings["sizing"]
    caps = [
        portfolio_value * sizing["max_single_position_pct"],
        float(row.get("dollar_volume", 0)) * sizing["max_position_pct_current_day_dollar_volume"],
        float(row.get("avg_dollar_volume_20d", 0)) * sizing["max_position_pct_avg_20d_dollar_volume"],
        sizing["fixed_dollar_cap_per_ticker"],
    ]
    return max(0, min(caps))


def score_position_multiplier(score: float, settings: dict) -> float:
    tier = conviction_tier(score, settings)
    if tier == "full":
        return 1.0
    if tier == "half":
        return 0.5
    if tier == "starter":
        return settings["sizing"]["starter_position_pct_of_target"]
    return 0.0


def calculate_position_size(row: pd.Series, score: float, portfolio_value: float, settings: dict) -> dict:
    target = target_position_dollars(row, portfolio_value, settings)
    allowed_dollars = target * score_position_multiplier(score, settings)
    price = float(row.get("close", 0))
    shares = math.floor(allowed_dollars / price) if price > 0 else 0
    return {
        "target_dollars": round(target, 2),
        "allowed_dollars": round(shares * price, 2),
        "shares": shares,
        "conviction": conviction_tier(score, settings),
    }


def staged_entry_plan(target_shares: int) -> list[int]:
    stages = [0.25, 0.25, 0.25, 0.25]
    planned = [math.floor(target_shares * pct) for pct in stages]
    planned[-1] += target_shares - sum(planned)
    return planned


def can_average_down(signal_score_increased: bool, catalyst_valid: bool, level2_ok: bool, guardrails_ok: bool, settings: dict) -> bool:
    if not settings["sizing"]["allow_averaging_down"]:
        return False
    return signal_score_increased and catalyst_valid and level2_ok and guardrails_ok
