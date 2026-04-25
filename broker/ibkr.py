from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class IBKRPaperPlaceholder:
    """
    Future path:
    Python app -> Trader Workstation or IB Gateway -> IBKR paper account.

    This class intentionally does not connect to live trading and does not place
    real orders. Later, it can be replaced with the official TWS API client.
    Market depth would come from reqMktDepth when paper trading is explicitly enabled.
    """

    def __init__(self, settings: dict):
        self.settings = settings
        self.connected = False

    def connect_paper(self) -> bool:
        if self.settings["portfolio"]["live_trading_enabled"]:
            raise RuntimeError("Live trading is disabled in this MVP.")
        logger.info("Paper connection placeholder. No real IBKR connection opened.")
        self.connected = True
        return self.connected

    def get_account_summary(self) -> dict:
        return {"status": "placeholder", "paper_trading_enabled": self.settings["portfolio"]["paper_trading_enabled"]}

    def get_market_data(self, ticker: str) -> dict:
        return {"ticker": ticker, "status": "placeholder"}

    def get_level2_data(self, ticker: str) -> dict:
        return {"ticker": ticker, "status": "placeholder", "source": "future reqMktDepth"}

    def place_limit_order_paper(self, ticker: str, side: str, shares: int, limit_price: float) -> dict:
        if not self.settings["portfolio"]["paper_trading_enabled"]:
            return {"accepted": False, "reason": "paper trading disabled by default"}
        return {"accepted": False, "reason": "placeholder only; no orders sent"}

    def cancel_order(self, order_id: str) -> dict:
        return {"cancelled": False, "order_id": order_id, "reason": "placeholder only"}

    def disconnect(self) -> None:
        self.connected = False
