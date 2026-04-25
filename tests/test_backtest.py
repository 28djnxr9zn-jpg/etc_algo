import pandas as pd

from backtests.backtest import run_backtest
from backtests.fills import simulate_entry_fill
from database.db import load_settings
from monitoring.level2 import estimate_executable_shares
from scanners.universe import MarketFrames


def test_level2_fill_estimation():
    assert estimate_executable_shares(100000, 10) == 10000


def test_partial_fill_behavior():
    cfg = load_settings()
    row = pd.Series({"best_ask": 0.01, "bid_ask_spread_percent": 5, "estimated_buy_fill_shares": 1000, "volume": 100000})
    fill = simulate_entry_fill(row, 5000, 0.01, cfg)
    assert fill["filled_shares"] == 1000
    assert fill["partial_fill"]


def test_backtest_trade_creation():
    cfg = load_settings()
    prices = pd.DataFrame([
        {"ticker": "ALFA", "date": "2026-01-01", "open": 0.002, "high": 0.002, "low": 0.002, "close": 0.002, "volume": 1_000_000, "dollar_volume": 2000},
        {"ticker": "ALFA", "date": "2026-01-02", "open": 0.002, "high": 0.006, "low": 0.002, "close": 0.005, "volume": 6_000_000, "dollar_volume": 30000},
        {"ticker": "ALFA", "date": "2026-01-03", "open": 0.005, "high": 0.008, "low": 0.004, "close": 0.007, "volume": 7_000_000, "dollar_volume": 49000},
    ])
    metadata = pd.DataFrame([{"ticker": "ALFA", "date": "2026-01-02", "otc_tier": "Pink Current", "caveat_emptor_flag": 0, "expert_market_flag": 0, "grey_market_flag": 0, "reverse_split_flag": 0, "dilution_flag": 0, "shell_risk_flag": 0, "promotion_risk_flag": 0}])
    catalysts = pd.DataFrame([{"ticker": "ALFA", "date": "2026-01-02", "news_flag": 1, "filing_flag": 1, "social_spike_flag": 1, "catalyst_text": "test", "catalyst_strength_score": 90}])
    level2 = pd.DataFrame([{"ticker": "ALFA", "timestamp": "2026-01-02 10:00:00", "best_bid": 0.0049, "best_ask": 0.005, "bid_ask_spread_percent": 2, "bid_depth_shares": 1000000, "ask_depth_shares": 1000000, "estimated_buy_fill_shares": 100000, "estimated_sell_fill_shares": 100000, "order_book_imbalance": 0}])
    metrics, trades = run_backtest(MarketFrames(prices, metadata, catalysts, level2), cfg)
    assert metrics["number_of_trades"] >= 1
    assert trades[0]["ticker"] == "ALFA"


def test_backtest_price_only_data_with_missing_flags_does_not_crash():
    cfg = load_settings()
    cfg["tradable"]["require_catalyst"] = False
    prices = pd.DataFrame([
        {"ticker": "PENY", "date": "2026-01-01", "open": 0.01, "high": 0.012, "low": 0.009, "close": 0.01, "volume": 1_000_000, "dollar_volume": 10_000},
        {"ticker": "PENY", "date": "2026-01-02", "open": 0.01, "high": 0.02, "low": 0.01, "close": 0.02, "volume": 6_000_000, "dollar_volume": 120_000},
        {"ticker": "PENY", "date": "2026-01-03", "open": 0.021, "high": 0.022, "low": 0.018, "close": 0.02, "volume": 5_000_000, "dollar_volume": 100_000},
    ])
    metadata = pd.DataFrame([{"ticker": "PENY", "date": "2026-01-02", "otc_tier": "Unknown"}])
    catalysts = pd.DataFrame([{"ticker": "PENY", "date": "2026-01-02", "catalyst_text": "price-only"}])
    metrics, trades = run_backtest(MarketFrames(prices, metadata, catalysts, pd.DataFrame()), cfg)
    assert metrics["number_of_trades"] >= 0
    assert isinstance(trades, list)
