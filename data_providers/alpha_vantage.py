from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import sleep

import pandas as pd
import requests


BASE_URL = "https://www.alphavantage.co/query"


@dataclass
class FetchResult:
    prices: pd.DataFrame
    metadata: pd.DataFrame
    catalysts: pd.DataFrame
    errors: list[str]


def normalize_symbols(symbols_text: str) -> list[str]:
    symbols = []
    for raw in symbols_text.replace("\n", ",").split(","):
        symbol = raw.strip().upper()
        if symbol:
            symbols.append(symbol)
    return sorted(set(symbols))


def fetch_daily_prices(symbol: str, api_key: str, outputsize: str = "compact") -> pd.DataFrame:
    response = requests.get(
        BASE_URL,
        params={
            "function": "TIME_SERIES_DAILY_ADJUSTED",
            "symbol": symbol,
            "outputsize": outputsize,
            "apikey": api_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "Error Message" in payload:
        raise ValueError(payload["Error Message"])
    if "Note" in payload:
        raise ValueError(payload["Note"])
    if "Information" in payload:
        raise ValueError(payload["Information"])

    series = payload.get("Time Series (Daily)", {})
    if not series:
        raise ValueError(f"No daily price series returned for {symbol}")

    rows = []
    for date, values in series.items():
        close = float(values["4. close"])
        volume = int(float(values["6. volume"]))
        rows.append(
            {
                "ticker": symbol,
                "date": date,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": close,
                "volume": volume,
                "dollar_volume": close * volume,
            }
        )
    return pd.DataFrame(rows).sort_values(["ticker", "date"])


def neutral_metadata(symbols: list[str]) -> pd.DataFrame:
    today = datetime.now().strftime("%Y-%m-%d")
    return pd.DataFrame(
        [
            {
                "ticker": symbol,
                "date": today,
                "otc_tier": "Unknown",
                "caveat_emptor_flag": 0,
                "expert_market_flag": 0,
                "grey_market_flag": 0,
                "reverse_split_flag": 0,
                "dilution_flag": 0,
                "shell_risk_flag": 0,
                "promotion_risk_flag": 0,
            }
            for symbol in symbols
        ]
    )


def neutral_catalysts(symbols: list[str]) -> pd.DataFrame:
    today = datetime.now().strftime("%Y-%m-%d")
    return pd.DataFrame(
        [
            {
                "ticker": symbol,
                "date": today,
                "news_flag": 0,
                "filing_flag": 0,
                "social_spike_flag": 0,
                "catalyst_text": "No catalyst data from price provider",
                "catalyst_strength_score": 0,
            }
            for symbol in symbols
        ]
    )


def fetch_symbols(symbols: list[str], api_key: str, outputsize: str = "compact", pause_seconds: float = 12.0) -> FetchResult:
    frames = []
    errors = []
    for index, symbol in enumerate(symbols):
        try:
            frames.append(fetch_daily_prices(symbol, api_key, outputsize=outputsize))
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
        if index < len(symbols) - 1:
            sleep(pause_seconds)

    prices = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    successful_symbols = sorted(prices["ticker"].unique()) if not prices.empty else []
    return FetchResult(
        prices=prices,
        metadata=neutral_metadata(successful_symbols),
        catalysts=neutral_catalysts(successful_symbols),
        errors=errors,
    )
