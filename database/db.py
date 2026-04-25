from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "otc_algo.sqlite"
SCHEMA_PATH = ROOT / "database" / "schema.sql"
SETTINGS_PATH = ROOT / "config" / "settings.yaml"

logger = logging.getLogger(__name__)


def load_settings(path: Path | str = SETTINGS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def get_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def init_db(db_path: Path | str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    logger.info("Initialized database at %s", db_path)


def load_csv_table(conn: sqlite3.Connection, csv_path: Path, table: str) -> None:
    frame = pd.read_csv(csv_path)
    frame.to_sql(table, conn, if_exists="append", index=False)


def load_sample_data(db_path: Path | str = DB_PATH) -> None:
    raw_dir = ROOT / "data" / "raw"
    init_db(db_path)
    with get_connection(db_path) as conn:
        for table in ["prices", "otc_metadata", "catalysts", "level2_snapshots"]:
            conn.execute(f"DELETE FROM {table}")
        load_csv_table(conn, raw_dir / "sample_prices.csv", "prices")
        load_csv_table(conn, raw_dir / "sample_metadata.csv", "otc_metadata")
        load_csv_table(conn, raw_dir / "sample_catalysts.csv", "catalysts")
        load_csv_table(conn, raw_dir / "sample_level2.csv", "level2_snapshots")
        if (raw_dir / "sample_universe.csv").exists():
            conn.execute("DELETE FROM universe_tickers")
            load_csv_table(conn, raw_dir / "sample_universe.csv", "universe_tickers")
    logger.info("Loaded sample data into %s", db_path)


def replace_table_rows(frame: pd.DataFrame, table: str, db_path: Path | str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(f"DELETE FROM {table}")
        frame.to_sql(table, conn, if_exists="append", index=False)


def upsert_universe(universe_name: str, tickers: list[str], source: str = "manual", notes: str = "", db_path: Path | str = DB_PATH) -> None:
    init_db(db_path)
    rows = [
        {
            "universe_name": universe_name,
            "ticker": ticker.strip().upper(),
            "source": source,
            "notes": notes,
            "active": 1,
        }
        for ticker in sorted(set(tickers))
        if ticker.strip()
    ]
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM universe_tickers WHERE universe_name = ?", (universe_name,))
        if rows:
            pd.DataFrame(rows).to_sql("universe_tickers", conn, if_exists="append", index=False)


def list_universes(db_path: Path | str = DB_PATH) -> list[str]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        frame = pd.read_sql_query(
            "SELECT universe_name FROM universe_tickers WHERE active = 1 GROUP BY universe_name ORDER BY universe_name",
            conn,
        )
    return frame["universe_name"].tolist()


def get_universe_tickers(universe_name: str, db_path: Path | str = DB_PATH) -> list[str]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        frame = pd.read_sql_query(
            "SELECT ticker FROM universe_tickers WHERE universe_name = ? AND active = 1 ORDER BY ticker",
            conn,
            params=(universe_name,),
        )
    return frame["ticker"].tolist()


def read_table(table: str, db_path: Path | str = DB_PATH) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(f"SELECT * FROM {table}", conn)
