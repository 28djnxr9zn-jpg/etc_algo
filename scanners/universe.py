from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from utils import safe_float, safe_int


RISK_FLAG_COLUMNS = [
    "expert_market_flag",
    "grey_market_flag",
    "caveat_emptor_flag",
    "reverse_split_flag",
    "dilution_flag",
]


@dataclass
class MarketFrames:
    prices: pd.DataFrame
    metadata: pd.DataFrame
    catalysts: pd.DataFrame
    level2: pd.DataFrame | None = None


def in_entry_price_range(price: float, settings: dict) -> bool:
    return settings["entry"]["min_price"] <= float(price) <= settings["entry"]["max_price"]


def latest_rows_by_ticker(frame: pd.DataFrame, date_column: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    sorted_frame = frame.sort_values([date_column])
    return sorted_frame.groupby("ticker", as_index=False).tail(1)


def add_rolling_stats(prices: pd.DataFrame) -> pd.DataFrame:
    prices = prices.copy()
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values(["ticker", "date"])
    grouped = prices.groupby("ticker", group_keys=False)
    prices["avg_volume_20d"] = grouped["volume"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=1).mean().fillna(s)
    )
    prices["avg_dollar_volume_20d"] = grouped["dollar_volume"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=1).mean().fillna(s)
    )
    prices["close_5d_ma"] = grouped["close"].transform(lambda s: s.rolling(5, min_periods=1).mean())
    prices["prior_close"] = grouped["close"].shift(1)
    prices["momentum_pct"] = ((prices["close"] - prices["prior_close"]) / prices["prior_close"]).replace([pd.NA, pd.NaT], 0).fillna(0) * 100
    return prices


def build_daily_snapshot(frames: MarketFrames, as_of_date: str | None = None) -> pd.DataFrame:
    prices = add_rolling_stats(frames.prices)
    if as_of_date:
        prices = prices[prices["date"] <= pd.to_datetime(as_of_date)]
    latest_prices = latest_rows_by_ticker(prices, "date")

    metadata = frames.metadata.copy()
    if not metadata.empty:
        metadata["date"] = pd.to_datetime(metadata["date"])
        if as_of_date:
            metadata = metadata[metadata["date"] <= pd.to_datetime(as_of_date)]
        metadata = latest_rows_by_ticker(metadata, "date").drop(columns=["date"], errors="ignore")

    catalysts = frames.catalysts.copy()
    if not catalysts.empty:
        catalysts["date"] = pd.to_datetime(catalysts["date"])
        if as_of_date:
            catalysts = catalysts[catalysts["date"] <= pd.to_datetime(as_of_date)]
        catalysts = latest_rows_by_ticker(catalysts, "date").drop(columns=["date"], errors="ignore")

    snapshot = latest_prices
    if not metadata.empty and "ticker" in metadata:
        snapshot = snapshot.merge(metadata, on="ticker", how="left")
    if not catalysts.empty and "ticker" in catalysts:
        snapshot = snapshot.merge(catalysts, on="ticker", how="left")

    if frames.level2 is not None and not frames.level2.empty:
        level2 = frames.level2.copy()
        level2["timestamp"] = pd.to_datetime(level2["timestamp"])
        if as_of_date:
            level2 = level2[level2["timestamp"].dt.date <= pd.to_datetime(as_of_date).date()]
        level2 = latest_rows_by_ticker(level2, "timestamp").drop(columns=["timestamp"], errors="ignore")
        snapshot = snapshot.merge(level2, on="ticker", how="left")

    for column in RISK_FLAG_COLUMNS + ["news_flag", "filing_flag", "social_spike_flag"]:
        if column in snapshot:
            snapshot[column] = snapshot[column].fillna(0).astype(int)
    if "catalyst_strength_score" not in snapshot:
        snapshot["catalyst_strength_score"] = 0
    snapshot["catalyst_strength_score"] = snapshot["catalyst_strength_score"].fillna(0)
    return snapshot


def passes_watchlist(row: pd.Series, settings: dict) -> tuple[bool, str]:
    if not in_entry_price_range(row["close"], settings):
        return False, "outside entry price range"
    if row["avg_volume_20d"] < settings["watchlist"]["min_avg_volume_20d"]:
        return False, "20d average volume too low"
    if row["avg_dollar_volume_20d"] < settings["watchlist"]["min_avg_dollar_volume_20d"]:
        return False, "20d average dollar volume too low"
    if safe_int(row.get("expert_market_flag", 0)):
        return False, "expert market excluded"
    if safe_int(row.get("grey_market_flag", 0)):
        return False, "grey market excluded"
    if safe_int(row.get("caveat_emptor_flag", 0)):
        return False, "caveat emptor excluded"
    return True, "passed watchlist"


def catalyst_is_active(row: pd.Series) -> bool:
    flags = [row.get("news_flag", 0), row.get("filing_flag", 0), row.get("social_spike_flag", 0)]
    return any(safe_int(flag) for flag in flags) or safe_float(row.get("catalyst_strength_score", 0)) > 0


def has_sufficient_level2(row: pd.Series, settings: dict) -> bool:
    if "bid_ask_spread_percent" not in row or pd.isna(row.get("bid_ask_spread_percent")):
        return True
    if float(row["bid_ask_spread_percent"]) > settings["execution"]["max_spread_pct"]:
        return False
    return safe_int(row.get("estimated_buy_fill_shares", 0)) > 0 and safe_int(row.get("estimated_sell_fill_shares", 0)) > 0


def passes_tradable(row: pd.Series, settings: dict) -> tuple[bool, str]:
    if not in_entry_price_range(row["close"], settings):
        return False, "outside entry price range"
    breakout_multiple = row["volume"] / max(row["avg_volume_20d"], 1)
    if breakout_multiple < settings["tradable"]["min_volume_breakout_multiple"]:
        return False, "volume breakout too small"
    if row["dollar_volume"] < settings["tradable"]["min_current_dollar_volume"]:
        return False, "current dollar volume too low"
    if settings["tradable"]["require_catalyst"] and not catalyst_is_active(row):
        return False, "missing catalyst"
    if safe_int(row.get("reverse_split_flag", 0)):
        return False, "reverse split flag"
    if safe_int(row.get("dilution_flag", 0)):
        return False, "dilution flag"
    if not has_sufficient_level2(row, settings):
        return False, "insufficient level 2 liquidity or wide spread"
    return True, "passed tradable"


def scan_universe(frames: MarketFrames, settings: dict, as_of_date: str | None = None) -> pd.DataFrame:
    snapshot = build_daily_snapshot(frames, as_of_date)
    rows = []
    for _, row in snapshot.iterrows():
        watchlist, watch_reason = passes_watchlist(row, settings)
        tradable, trade_reason = passes_tradable(row, settings) if watchlist else (False, watch_reason)
        output = row.to_dict()
        output["passed_watchlist"] = watchlist
        output["passed_tradable"] = tradable
        output["reason"] = trade_reason if not tradable else "tradable candidate"
        rows.append(output)
    return pd.DataFrame(rows)
