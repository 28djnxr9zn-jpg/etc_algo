from __future__ import annotations

from utils import safe_int


def should_exit_for_price_above_entry_range(current_price: float, settings: dict) -> bool:
    return bool(settings["risk_exits"]["exit_on_price_above_entry_range"]) and current_price > settings["entry"]["max_price"]


def check_risk_exit(position: dict, observation: dict, settings: dict) -> tuple[bool, str]:
    current_price = float(observation.get("close", observation.get("best_bid", 0)))
    if should_exit_for_price_above_entry_range(current_price, settings):
        return True, "price above entry range exit enabled"

    high = max(float(position.get("highest_price_since_entry", current_price)), current_price)
    if high > 0:
        drop_from_high = (high - current_price) / high * 100
        if drop_from_high >= settings["risk_exits"]["massive_drop_from_intraday_high_pct"]:
            return True, "massive drop from intraday high"

    last_scan_price = float(position.get("last_scan_price", current_price))
    if last_scan_price > 0:
        drop_from_scan = (last_scan_price - current_price) / last_scan_price * 100
        if drop_from_scan >= settings["risk_exits"]["massive_drop_from_last_scan_pct"]:
            return True, "massive drop from last 15-minute scan"

    if settings["risk_exits"]["exit_on_volume_collapse"]:
        breakout_volume = max(float(position.get("breakout_day_volume", 0)), 1)
        current_volume = float(observation.get("volume", breakout_volume))
        collapse_threshold = settings["risk_exits"]["volume_collapse_pct_of_breakout_volume"] / 100
        if current_volume < breakout_volume * collapse_threshold:
            return True, "volume collapse"

    if settings["risk_exits"]["exit_on_l2_bid_support_collapse"]:
        if observation.get("estimated_sell_fill_shares", 1) <= 0 or observation.get("bid_depth_shares", 1) <= 0:
            return True, "level 2 bid support collapse"

    if settings["risk_exits"]["exit_on_extreme_spread"]:
        if observation.get("bid_ask_spread_percent", 0) > settings["execution"]["max_spread_pct"]:
            return True, "extreme spread"

    if settings["risk_exits"]["exit_on_dilution_flag"] and safe_int(observation.get("dilution_flag", 0)):
        return True, "dilution flag appeared"

    if settings["risk_exits"]["exit_on_reverse_split_flag"] and safe_int(observation.get("reverse_split_flag", 0)):
        return True, "reverse split flag appeared"

    return False, "hold"


def portfolio_guardrails_ok(open_positions: int, new_positions_today: int, total_otc_exposure: float, portfolio_value: float, settings: dict) -> tuple[bool, str]:
    portfolio = settings["portfolio"]
    if portfolio["global_stop_trading"]:
        return False, "global stop trading flag"
    if portfolio["flatten_all_positions"]:
        return False, "flatten all positions flag"
    if open_positions >= portfolio["max_open_positions"]:
        return False, "max open positions reached"
    if new_positions_today >= portfolio["max_new_positions_per_day"]:
        return False, "max new positions per day reached"
    if portfolio_value > 0 and total_otc_exposure / portfolio_value >= portfolio["max_total_otc_exposure_pct"]:
        return False, "max OTC exposure reached"
    return True, "guardrails ok"
