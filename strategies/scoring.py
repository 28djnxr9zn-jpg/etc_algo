from __future__ import annotations

import pandas as pd


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def safe_int(value, default: int = 0) -> int:
    if pd.isna(value):
        return default
    return int(value)


def score_volume_breakout(row: pd.Series) -> float:
    multiple = float(row.get("volume", 0)) / max(float(row.get("avg_volume_20d", 1)), 1)
    return clamp((multiple / 5) * 100)


def score_catalyst(row: pd.Series) -> float:
    base = float(row.get("catalyst_strength_score", 0))
    flag_bonus = 0
    for flag in ["news_flag", "filing_flag", "social_spike_flag"]:
        flag_bonus += 10 if safe_int(row.get(flag, 0)) else 0
    return clamp(base + flag_bonus)


def score_otc_quality(row: pd.Series) -> float:
    tier = str(row.get("otc_tier", "")).lower()
    if "otcqx" in tier:
        return 100
    if "otcqb" in tier:
        return 80
    if "pink current" in tier:
        return 65
    if "pink limited" in tier:
        return 40
    return 25


def score_risk_flags(row: pd.Series) -> float:
    score = 100
    penalties = {
        "reverse_split_flag": 40,
        "dilution_flag": 40,
        "shell_risk_flag": 20,
        "promotion_risk_flag": 20,
        "caveat_emptor_flag": 100,
        "expert_market_flag": 100,
        "grey_market_flag": 100,
    }
    for flag, penalty in penalties.items():
        if safe_int(row.get(flag, 0)):
            score -= penalty
    return clamp(score)


def score_momentum(row: pd.Series) -> float:
    momentum = float(row.get("momentum_pct", 0))
    if momentum <= 0:
        return 20
    return clamp(20 + momentum * 4)


def calculate_signal_score(row: pd.Series, settings: dict) -> float:
    weights = settings["scoring"]
    score = (
        score_volume_breakout(row) * weights["volume_breakout_weight"]
        + score_catalyst(row) * weights["catalyst_weight"]
        + score_otc_quality(row) * weights["otc_quality_weight"]
        + score_risk_flags(row) * weights["risk_flags_weight"]
        + score_momentum(row) * weights["momentum_weight"]
    )
    return round(clamp(score), 2)


def conviction_tier(score: float, settings: dict) -> str:
    if score >= settings["scoring"]["full_position_score"]:
        return "full"
    if score >= settings["scoring"]["half_position_score"]:
        return "half"
    if score >= settings["scoring"]["starter_position_score"]:
        return "starter"
    return "none"
