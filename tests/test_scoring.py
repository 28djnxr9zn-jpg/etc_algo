import pandas as pd

from database.db import load_settings
from strategies.scoring import calculate_signal_score, conviction_tier


def test_scoring_model():
    cfg = load_settings()
    row = pd.Series({
        "volume": 5_000_000,
        "avg_volume_20d": 1_000_000,
        "catalyst_strength_score": 80,
        "news_flag": 1,
        "filing_flag": 1,
        "social_spike_flag": 1,
        "otc_tier": "OTCQB",
        "reverse_split_flag": 0,
        "dilution_flag": 0,
        "shell_risk_flag": 0,
        "promotion_risk_flag": 0,
        "momentum_pct": 20,
    })
    score = calculate_signal_score(row, cfg)
    assert 80 <= score <= 100
    assert conviction_tier(91, cfg) == "full"
    assert conviction_tier(80, cfg) == "half"
    assert conviction_tier(65, cfg) == "starter"
    assert conviction_tier(40, cfg) == "none"
