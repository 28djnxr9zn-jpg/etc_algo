from __future__ import annotations

import logging
from datetime import datetime, time

import pandas as pd

from monitoring.risk_checks import check_risk_exit

logger = logging.getLogger(__name__)


def is_market_hours(now: datetime) -> bool:
    return now.weekday() < 5 and time(9, 30) <= now.time() <= time(16, 0)


class IntradayMonitor:
    def __init__(self, settings: dict):
        self.settings = settings

    def observe_positions(self, positions: list[dict], observations: pd.DataFrame, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now()
        if self.settings["monitoring"]["market_hours_only"] and not is_market_hours(now):
            logger.info("Skipping monitor outside market hours: %s", now)
            return []

        alerts = []
        for position in positions:
            ticker = position["ticker"]
            ticker_obs = observations[observations["ticker"] == ticker]
            if ticker_obs.empty:
                logger.info("No observation for %s", ticker)
                continue
            observation = ticker_obs.iloc[-1].to_dict()
            should_exit, reason = check_risk_exit(position, observation, self.settings)
            alert = {
                "timestamp": now.isoformat(),
                "ticker": ticker,
                "should_exit": should_exit,
                "reason": reason,
                "live_order_sent": False,
            }
            logger.info("Monitor observation: %s", alert)
            alerts.append(alert)
        return alerts


def run_monitor_sim(positions: list[dict], observations: pd.DataFrame, settings: dict) -> list[dict]:
    monitor = IntradayMonitor(settings)
    return monitor.observe_positions(positions, observations, now=datetime.now().replace(hour=10, minute=0))
