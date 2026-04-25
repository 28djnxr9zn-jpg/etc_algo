from __future__ import annotations

import math

from utils import safe_float, safe_int


def split_order(total_shares: int, slices: int = 4) -> list[int]:
    if total_shares <= 0:
        return []
    base = total_shares // slices
    orders = [base for _ in range(slices)]
    orders[-1] += total_shares - sum(orders)
    return [order for order in orders if order > 0]


def simulate_entry_fill(row, desired_shares: int, signal_price: float, settings: dict) -> dict:
    if desired_shares <= 0:
        return {"filled_shares": 0, "avg_fill_price": 0, "partial_fill": False, "rejected": True, "reason": "no desired shares"}

    spread = float(row.get("bid_ask_spread_percent", settings["execution"]["max_spread_pct"]))
    if spread > settings["execution"]["max_spread_pct"]:
        return {"filled_shares": 0, "avg_fill_price": 0, "partial_fill": False, "rejected": True, "reason": "spread too wide"}

    best_ask = float(row.get("best_ask", row.get("close", signal_price)))
    max_ask = signal_price * (1 + settings["execution"]["max_chase_pct_above_signal_price"] / 100)
    if best_ask > max_ask:
        return {"filled_shares": 0, "avg_fill_price": 0, "partial_fill": False, "rejected": True, "reason": "ask moved above chase limit"}

    available = safe_int(row.get("estimated_buy_fill_shares", 0))
    if available <= 0:
        daily_cap = safe_int(safe_float(row.get("volume", 0)) * 0.01)
        available = max(0, daily_cap)

    filled = min(desired_shares, available)
    if filled <= 0:
        return {"filled_shares": 0, "avg_fill_price": 0, "partial_fill": False, "rejected": True, "reason": "insufficient liquidity"}

    return {
        "filled_shares": filled,
        "avg_fill_price": best_ask,
        "partial_fill": filled < desired_shares,
        "rejected": False,
        "reason": "filled" if filled == desired_shares else "partial fill",
    }


def simulate_exit_fill(row, position_shares: int, settings: dict) -> dict:
    if position_shares <= 0:
        return {"filled_shares": 0, "avg_fill_price": 0, "partial_fill": False, "high_risk": False}
    best_bid = float(row.get("best_bid", row.get("close", 0)))
    available = safe_int(row.get("estimated_sell_fill_shares", 0))
    if available <= 0:
        available = math.floor(float(row.get("volume", 0)) * 0.005)
    filled = min(position_shares, max(0, available))
    slippage = settings["execution"]["simulated_slippage_pct"] / 100
    fill_price = max(0, best_bid * (1 - slippage))
    return {
        "filled_shares": filled,
        "avg_fill_price": fill_price,
        "partial_fill": filled < position_shares,
        "high_risk": available <= 0 or filled < position_shares,
    }
