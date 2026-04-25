import pandas as pd

from database.db import load_settings
from strategies.sizing import calculate_position_size


def test_conviction_based_sizing():
    cfg = load_settings()
    row = pd.Series({"close": 0.01, "dollar_volume": 100000, "avg_dollar_volume_20d": 50000})
    full = calculate_position_size(row, 95, 10000, cfg)
    half = calculate_position_size(row, 80, 10000, cfg)
    starter = calculate_position_size(row, 65, 10000, cfg)
    none = calculate_position_size(row, 20, 10000, cfg)
    assert full["allowed_dollars"] == 500
    assert half["allowed_dollars"] == 250
    assert starter["allowed_dollars"] == 125
    assert none["shares"] == 0


def test_liquidity_aware_sizing():
    cfg = load_settings()
    row = pd.Series({"close": 0.01, "dollar_volume": 1000, "avg_dollar_volume_20d": 1000})
    size = calculate_position_size(row, 95, 10000, cfg)
    assert size["allowed_dollars"] <= 100
