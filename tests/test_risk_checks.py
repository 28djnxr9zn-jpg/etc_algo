from database.db import load_settings
from monitoring.risk_checks import check_risk_exit, portfolio_guardrails_ok


def test_entry_price_range_applies_only_to_entries():
    cfg = load_settings()
    position = {"highest_price_since_entry": 0.06, "last_scan_price": 0.06, "breakout_day_volume": 1_000_000}
    observation = {"close": 0.06, "volume": 1_000_000, "estimated_sell_fill_shares": 1000, "bid_depth_shares": 1000, "bid_ask_spread_percent": 5}
    should_exit, reason = check_risk_exit(position, observation, cfg)
    assert not should_exit
    assert reason == "hold"


def test_stock_not_sold_merely_above_max_entry_price():
    cfg = load_settings()
    position = {"highest_price_since_entry": 0.08, "last_scan_price": 0.07, "breakout_day_volume": 1_000_000}
    observation = {"close": 0.07, "volume": 1_000_000, "estimated_sell_fill_shares": 1000, "bid_depth_shares": 1000, "bid_ask_spread_percent": 5}
    assert check_risk_exit(position, observation, cfg)[0] is False


def test_massive_drop_risk_exit():
    cfg = load_settings()
    position = {"highest_price_since_entry": 0.10, "last_scan_price": 0.10, "breakout_day_volume": 1_000_000}
    observation = {"close": 0.06, "volume": 1_000_000, "estimated_sell_fill_shares": 1000, "bid_depth_shares": 1000, "bid_ask_spread_percent": 5}
    should_exit, reason = check_risk_exit(position, observation, cfg)
    assert should_exit
    assert "drop" in reason


def test_volume_collapse_risk_exit():
    cfg = load_settings()
    position = {"highest_price_since_entry": 0.01, "last_scan_price": 0.01, "breakout_day_volume": 1_000_000}
    observation = {"close": 0.01, "volume": 100_000, "estimated_sell_fill_shares": 1000, "bid_depth_shares": 1000, "bid_ask_spread_percent": 5}
    should_exit, reason = check_risk_exit(position, observation, cfg)
    assert should_exit
    assert "volume" in reason


def test_portfolio_guardrails():
    cfg = load_settings()
    ok, _ = portfolio_guardrails_ok(0, 0, 0, 10000, cfg)
    assert ok
    ok, reason = portfolio_guardrails_ok(10, 0, 0, 10000, cfg)
    assert not ok
    assert "open positions" in reason
