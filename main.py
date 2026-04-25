from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from backtests.backtest import run_backtest
from database.db import DB_PATH, get_connection, init_db, load_sample_data, load_settings, read_table
from monitoring.intraday_monitor import run_monitor_sim
from scanners.universe import MarketFrames, scan_universe
from strategies.scoring import calculate_signal_score

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def load_frames() -> MarketFrames:
    return MarketFrames(
        prices=read_table("prices"),
        metadata=read_table("otc_metadata"),
        catalysts=read_table("catalysts"),
        level2=read_table("level2_snapshots"),
    )


def command_scan(settings: dict) -> None:
    frames = load_frames()
    scan = scan_universe(frames, settings)
    if scan.empty:
        print("No data found. Run: python main.py load-sample-data")
        return
    scan["signal_score"] = scan.apply(lambda row: calculate_signal_score(row, settings), axis=1)
    columns = ["ticker", "close", "volume", "avg_volume_20d", "dollar_volume", "passed_watchlist", "passed_tradable", "signal_score", "reason"]
    print(scan[columns].sort_values("signal_score", ascending=False).to_string(index=False))


def command_backtest(settings: dict) -> None:
    metrics, trades = run_backtest(load_frames(), settings)
    print("Backtest metrics")
    for key, value in metrics.items():
        print(f"{key}: {value}")
    print("\nTrades")
    print(pd.DataFrame(trades).to_string(index=False) if trades else "No trades")


def command_monitor_sim(settings: dict) -> None:
    frames = load_frames()
    scan = scan_universe(frames, settings)
    positions = [
        {
            "ticker": "ALFA",
            "entry_timestamp": "2026-01-05",
            "avg_cost": 0.003,
            "shares": 50000,
            "highest_price_since_entry": 0.007,
            "breakout_day_volume": 7000000,
            "last_scan_price": 0.006,
        }
    ]
    alerts = run_monitor_sim(positions, scan, settings)
    print(pd.DataFrame(alerts).to_string(index=False) if alerts else "No alerts")


def main() -> None:
    parser = argparse.ArgumentParser(description="OTC/sub-penny scanner and backtester")
    parser.add_argument("command", choices=["init-db", "load-sample-data", "scan", "backtest", "monitor-sim"])
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "init-db":
        init_db(DB_PATH)
        print(f"Initialized {DB_PATH}")
    elif args.command == "load-sample-data":
        load_sample_data(DB_PATH)
        print(f"Loaded sample data into {DB_PATH}")
    elif args.command == "scan":
        command_scan(settings)
    elif args.command == "backtest":
        command_backtest(settings)
    elif args.command == "monitor-sim":
        command_monitor_sim(settings)


if __name__ == "__main__":
    main()
