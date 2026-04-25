from __future__ import annotations

import pandas as pd


def max_drawdown(values: list[float]) -> float:
    peak = values[0] if values else 0
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak)
    return round(worst * 100, 2)


def calculate_metrics(starting_cash: float, cash: float, open_positions: dict, trades: list[dict], equity_curve: list[float] | list[dict], partial_fills: int, liquidity_rejections: int) -> dict:
    values = [row["portfolio_value"] for row in equity_curve] if equity_curve and isinstance(equity_curve[0], dict) else equity_curve
    closed = [trade for trade in trades if trade.get("exit_timestamp")]
    wins = [trade for trade in closed if trade.get("realized_gain_loss", 0) > 0]
    losses = [trade for trade in closed if trade.get("realized_gain_loss", 0) < 0]
    holding_periods = []
    for trade in closed:
        entry = pd.to_datetime(trade["entry_timestamp"])
        exit_time = pd.to_datetime(trade["exit_timestamp"])
        holding_periods.append((exit_time - entry).days)
    return {
        "portfolio_value": round(values[-1] if values else cash, 2),
        "total_return_pct": round(((values[-1] - starting_cash) / starting_cash) * 100, 2) if values else 0,
        "win_rate_pct": round(len(wins) / len(closed) * 100, 2) if closed else 0,
        "average_gain": round(pd.Series([t["realized_gain_loss"] for t in wins]).mean(), 2) if wins else 0,
        "average_loss": round(pd.Series([t["realized_gain_loss"] for t in losses]).mean(), 2) if losses else 0,
        "max_drawdown_pct": max_drawdown(values),
        "number_of_trades": len(trades),
        "average_holding_period_days": round(pd.Series(holding_periods).mean(), 2) if holding_periods else 0,
        "partial_fill_pct": round(partial_fills / len(trades) * 100, 2) if trades else 0,
        "trades_rejected_due_to_liquidity": liquidity_rejections,
        "positions_still_open": len(open_positions),
        "largest_winner": max([t.get("realized_gain_loss", 0) for t in closed], default=0),
        "largest_loser": min([t.get("realized_gain_loss", 0) for t in closed], default=0),
    }
