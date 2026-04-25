from __future__ import annotations

import logging

import pandas as pd

from backtests.fills import simulate_entry_fill, simulate_exit_fill
from backtests.metrics import calculate_metrics
from monitoring.risk_checks import check_risk_exit, portfolio_guardrails_ok
from scanners.universe import MarketFrames, scan_universe
from strategies.scoring import calculate_signal_score
from strategies.sizing import calculate_position_size

logger = logging.getLogger(__name__)


class Backtester:
    def __init__(self, frames: MarketFrames, settings: dict):
        self.frames = frames
        self.settings = settings
        self.starting_cash = float(settings["portfolio"]["starting_cash"])
        self.cash = self.starting_cash
        self.positions: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.equity_curve: list[float] = [self.starting_cash]
        self.partial_fills = 0
        self.liquidity_rejections = 0

    def portfolio_value(self, date: str | None = None) -> float:
        value = self.cash
        prices = self.frames.prices.copy()
        if date:
            prices = prices[pd.to_datetime(prices["date"]) <= pd.to_datetime(date)]
        latest = prices.sort_values("date").groupby("ticker", as_index=False).tail(1).set_index("ticker")
        for ticker, position in self.positions.items():
            close = float(latest.loc[ticker, "close"]) if ticker in latest.index else position["avg_cost"]
            value += position["shares"] * close
        return value

    def total_exposure(self) -> float:
        return sum(position["shares"] * position["avg_cost"] for position in self.positions.values())

    def try_entry(self, row: pd.Series, date: str, new_positions_today: int) -> int:
        ok, reason = portfolio_guardrails_ok(
            open_positions=len(self.positions),
            new_positions_today=new_positions_today,
            total_otc_exposure=self.total_exposure(),
            portfolio_value=self.portfolio_value(date),
            settings=self.settings,
        )
        if not ok:
            logger.info("Guardrail skipped %s: %s", row["ticker"], reason)
            return 0

        score = calculate_signal_score(row, self.settings)
        sizing = calculate_position_size(row, score, self.portfolio_value(date), self.settings)
        fill = simulate_entry_fill(row, sizing["shares"], float(row["close"]), self.settings)
        if fill["rejected"]:
            self.liquidity_rejections += 1
            return 0
        if fill["partial_fill"]:
            self.partial_fills += 1
        shares = int(fill["filled_shares"])
        cost = shares * float(fill["avg_fill_price"])
        if shares <= 0 or cost > self.cash:
            return 0

        ticker = row["ticker"]
        self.cash -= cost
        self.positions[ticker] = {
            "ticker": ticker,
            "entry_timestamp": date,
            "avg_cost": float(fill["avg_fill_price"]),
            "shares": shares,
            "position_dollars": cost,
            "highest_price_since_entry": float(row["close"]),
            "breakout_day_volume": int(row["volume"]),
            "last_scan_price": float(row["close"]),
            "current_status": "open",
        }
        self.trades.append({
            "ticker": ticker,
            "entry_timestamp": date,
            "exit_timestamp": None,
            "entry_price": float(fill["avg_fill_price"]),
            "exit_price": None,
            "shares": shares,
            "position_dollars": cost,
            "realized_gain_loss": None,
            "realized_gain_loss_pct": None,
            "exit_reason": None,
        })
        return 1

    def apply_daily_risk(self, daily_rows: pd.DataFrame, date: str) -> None:
        for ticker in list(self.positions.keys()):
            rows = daily_rows[daily_rows["ticker"] == ticker]
            if rows.empty:
                continue
            row = rows.iloc[-1].to_dict()
            position = self.positions[ticker]
            position["highest_price_since_entry"] = max(position["highest_price_since_entry"], float(row["close"]))
            should_exit, reason = check_risk_exit(position, row, self.settings)
            position["last_scan_price"] = float(row["close"])
            if not should_exit:
                continue
            fill = simulate_exit_fill(row, position["shares"], self.settings)
            if fill["filled_shares"] <= 0:
                continue
            proceeds = fill["filled_shares"] * fill["avg_fill_price"]
            self.cash += proceeds
            remaining = position["shares"] - fill["filled_shares"]
            realized = (fill["avg_fill_price"] - position["avg_cost"]) * fill["filled_shares"]
            for trade in self.trades:
                if trade["ticker"] == ticker and trade["exit_timestamp"] is None:
                    trade["exit_timestamp"] = date
                    trade["exit_price"] = fill["avg_fill_price"]
                    trade["realized_gain_loss"] = realized
                    trade["realized_gain_loss_pct"] = realized / trade["position_dollars"] * 100
                    trade["exit_reason"] = reason
                    break
            if remaining <= 0:
                del self.positions[ticker]
            else:
                position["shares"] = remaining

    def run(self) -> dict:
        dates = sorted(pd.to_datetime(self.frames.prices["date"]).dt.strftime("%Y-%m-%d").unique())
        for date in dates:
            scan = scan_universe(self.frames, self.settings, as_of_date=date)
            if scan.empty:
                continue
            scan["signal_score"] = scan.apply(lambda row: calculate_signal_score(row, self.settings), axis=1)
            self.apply_daily_risk(scan, date)
            candidates = scan[scan["passed_tradable"]].sort_values("signal_score", ascending=False)
            new_positions_today = 0
            for _, row in candidates.iterrows():
                if row["ticker"] in self.positions:
                    continue
                new_positions_today += self.try_entry(row, date, new_positions_today)
            self.equity_curve.append(self.portfolio_value(date))
        return calculate_metrics(self.starting_cash, self.cash, self.positions, self.trades, self.equity_curve, self.partial_fills, self.liquidity_rejections)


def run_backtest(frames: MarketFrames, settings: dict) -> tuple[dict, list[dict]]:
    backtester = Backtester(frames, settings)
    metrics = backtester.run()
    return metrics, backtester.trades
