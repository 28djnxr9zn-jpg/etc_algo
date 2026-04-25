from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from time import sleep

import pandas as pd

def ensure_event_loop() -> None:
    """Create an asyncio event loop for Streamlit worker threads if needed."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


# Streamlit runs app code inside ScriptRunner threads. ib_insync imports
# eventkit, which expects the current thread to already have an event loop.
ensure_event_loop()

from ib_insync import IB, Stock, util

from monitoring.level2 import enrich_level2_snapshot


MARKET_DATA_TYPES = {
    "Live": 1,
    "Frozen": 2,
    "Delayed": 3,
    "Delayed frozen": 4,
}


@dataclass
class IBKRConnectionConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 7
    readonly: bool = True


def connect_ibkr(config: IBKRConnectionConfig) -> IB:
    ensure_event_loop()
    ib = IB()
    ib.connect(config.host, config.port, clientId=config.client_id, readonly=config.readonly, timeout=8)
    return ib


def make_stock_contract(symbol: str, exchange: str = "SMART", currency: str = "USD", primary_exchange: str | None = None) -> Stock:
    contract = Stock(symbol.upper(), exchange, currency)
    if primary_exchange:
        contract.primaryExchange = primary_exchange
    return contract


def fetch_historical_daily_prices(
    symbols: list[str],
    config: IBKRConnectionConfig,
    exchange: str,
    primary_exchange: str | None,
    currency: str,
    duration: str,
    market_data_type: str,
    what_to_show: str,
) -> tuple[pd.DataFrame, list[str]]:
    errors: list[str] = []
    frames: list[pd.DataFrame] = []
    try:
        ib = connect_ibkr(config)
    except Exception as exc:
        return pd.DataFrame(), [
            f"Could not connect to IBKR at {config.host}:{config.port}. "
            "Open TWS or IB Gateway, log in, enable API socket clients, and confirm the API port. "
            f"Original error: {exc}"
        ]
    try:
        ib.reqMarketDataType(MARKET_DATA_TYPES[market_data_type])
        for symbol in symbols:
            try:
                contract = make_stock_contract(symbol, exchange=exchange, currency=currency, primary_exchange=primary_exchange)
                qualified = ib.qualifyContracts(contract)
                if not qualified:
                    errors.append(f"{symbol}: contract could not be qualified. Try exchange=SMART and blank primary exchange.")
                    continue
                contract = qualified[0]
                bars = ib.reqHistoricalData(
                    contract,
                    endDateTime="",
                    durationStr=duration,
                    barSizeSetting="1 day",
                    whatToShow=what_to_show,
                    useRTH=True,
                    formatDate=1,
                    keepUpToDate=False,
                )
                frame = util.df(bars)
                if frame is None or frame.empty:
                    errors.append(
                        f"{symbol}: no historical bars returned for conId={contract.conId}, "
                        f"exchange={contract.exchange}, primaryExchange={getattr(contract, 'primaryExchange', '')}. "
                        f"whatToShow={what_to_show}. Check market-data permissions, try Delayed data, "
                        "try MIDPOINT, or try a longer duration."
                    )
                    continue
                frame["ticker"] = symbol.upper()
                frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
                frame = frame.rename(columns={"barCount": "bar_count", "average": "average_price"})
                frame["dollar_volume"] = frame["close"] * frame["volume"]
                frames.append(frame[["ticker", "date", "open", "high", "low", "close", "volume", "dollar_volume"]])
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
    finally:
        ib.disconnect()

    prices = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return prices, errors


def fetch_level2_snapshot(
    symbol: str,
    config: IBKRConnectionConfig,
    settings: dict,
    exchange: str,
    primary_exchange: str | None,
    currency: str,
    rows: int,
    smart_depth: bool,
    market_data_type: str,
) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    try:
        ib = connect_ibkr(config)
    except Exception as exc:
        return None, [
            f"Could not connect to IBKR at {config.host}:{config.port}. "
            "Open TWS or IB Gateway, log in, enable API socket clients, and confirm the API port. "
            f"Original error: {exc}"
        ]
    try:
        ib.reqMarketDataType(MARKET_DATA_TYPES[market_data_type])
        contract = make_stock_contract(symbol, exchange=exchange, currency=currency, primary_exchange=primary_exchange)
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            return None, [f"{symbol}: contract could not be qualified. Try exchange=SMART and blank primary exchange."]
        contract = qualified[0]
        ticker = ib.reqMktDepth(contract, numRows=rows, isSmartDepth=smart_depth)
        sleep(4)
        ib.cancelMktDepth(contract, isSmartDepth=smart_depth)

        bid_rows = ticker.domBids or []
        ask_rows = ticker.domAsks or []
        if not bid_rows or not ask_rows:
            return None, [f"{symbol}: no depth rows returned. Check TWS permissions, subscriptions, and exchange mapping."]

        best_bid = max(float(row.price) for row in bid_rows)
        best_ask = min(float(row.price) for row in ask_rows)
        bid_depth = int(sum(float(row.size) for row in bid_rows if float(row.price) == best_bid))
        ask_depth = int(sum(float(row.size) for row in ask_rows if float(row.price) == best_ask))
        snapshot = enrich_level2_snapshot(
            {
                "ticker": symbol.upper(),
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "best_bid": best_bid,
                "best_ask": best_ask,
                "bid_depth_shares": bid_depth,
                "ask_depth_shares": ask_depth,
            },
            settings,
        )
        return snapshot, errors
    except Exception as exc:
        errors.append(f"{symbol}: {exc}")
        return None, errors
    finally:
        ib.disconnect()
