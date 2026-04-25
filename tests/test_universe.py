import pandas as pd

from database.db import load_settings
from scanners.universe import MarketFrames, in_entry_price_range, passes_tradable, passes_watchlist, scan_universe


def settings():
    return load_settings()


def sample_row(**overrides):
    row = {
        "ticker": "TEST",
        "close": 0.01,
        "volume": 4_000_000,
        "dollar_volume": 40_000,
        "avg_volume_20d": 1_000_000,
        "avg_dollar_volume_20d": 10_000,
        "expert_market_flag": 0,
        "grey_market_flag": 0,
        "caveat_emptor_flag": 0,
        "reverse_split_flag": 0,
        "dilution_flag": 0,
        "news_flag": 1,
        "filing_flag": 0,
        "social_spike_flag": 0,
        "catalyst_strength_score": 80,
        "bid_ask_spread_percent": 10,
        "estimated_buy_fill_shares": 10000,
        "estimated_sell_fill_shares": 10000,
    }
    row.update(overrides)
    return pd.Series(row)


def test_price_filter():
    cfg = settings()
    assert in_entry_price_range(0.0001, cfg)
    assert in_entry_price_range(0.05, cfg)
    assert not in_entry_price_range(0.08, cfg)


def test_watchlist_filter():
    passed, _ = passes_watchlist(sample_row(), settings())
    assert passed
    failed, reason = passes_watchlist(sample_row(avg_volume_20d=1000), settings())
    assert not failed
    assert "volume" in reason


def test_otc_exclusion_flags():
    passed, reason = passes_watchlist(sample_row(caveat_emptor_flag=1), settings())
    assert not passed
    assert "caveat" in reason


def test_tradable_filter():
    passed, _ = passes_tradable(sample_row(), settings())
    assert passed
    failed, reason = passes_tradable(sample_row(volume=2_000_000), settings())
    assert not failed
    assert "breakout" in reason
