from __future__ import annotations

import math

from utils import safe_float, safe_int


def spread_percent(best_bid: float, best_ask: float) -> float:
    if best_ask <= 0:
        return 100.0
    midpoint = (best_bid + best_ask) / 2
    if midpoint <= 0:
        return 100.0
    return round(((best_ask - best_bid) / midpoint) * 100, 2)


def order_book_imbalance(bid_depth_shares: int, ask_depth_shares: int) -> float:
    total = bid_depth_shares + ask_depth_shares
    if total <= 0:
        return 0.0
    return round((bid_depth_shares - ask_depth_shares) / total, 4)


def estimate_executable_shares(displayed_depth: int, participation_rate_pct: float) -> int:
    return max(0, math.floor(displayed_depth * (participation_rate_pct / 100)))


def enrich_level2_snapshot(snapshot: dict, settings: dict) -> dict:
    bid = float(snapshot["best_bid"])
    ask = float(snapshot["best_ask"])
    bid_depth = safe_int(snapshot.get("bid_depth_shares", 0))
    ask_depth = safe_int(snapshot.get("ask_depth_shares", 0))
    participation = settings["execution"]["max_order_pct_of_displayed_liquidity"]
    return {
        **snapshot,
        "bid_ask_spread_percent": spread_percent(bid, ask),
        "estimated_buy_fill_shares": estimate_executable_shares(ask_depth, participation),
        "estimated_sell_fill_shares": estimate_executable_shares(bid_depth, participation),
        "order_book_imbalance": order_book_imbalance(bid_depth, ask_depth),
    }


def level2_is_acceptable(row, settings: dict) -> bool:
    if row.get("bid_ask_spread_percent", 0) > settings["execution"]["max_spread_pct"]:
        return False
    return row.get("estimated_buy_fill_shares", 0) > 0 and row.get("estimated_sell_fill_shares", 0) > 0
