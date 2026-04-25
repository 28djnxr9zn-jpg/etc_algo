from __future__ import annotations

import pandas as pd


def safe_int(value, default: int = 0) -> int:
    if pd.isna(value):
        return default
    return int(value)


def safe_float(value, default: float = 0.0) -> float:
    if pd.isna(value):
        return default
    return float(value)
