CREATE TABLE IF NOT EXISTS prices (
  ticker TEXT NOT NULL,
  date TEXT NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume INTEGER NOT NULL,
  dollar_volume REAL NOT NULL,
  PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS intraday_prices (
  ticker TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  open REAL NOT NULL,
  high REAL NOT NULL,
  low REAL NOT NULL,
  close REAL NOT NULL,
  volume INTEGER NOT NULL,
  dollar_volume REAL NOT NULL,
  PRIMARY KEY (ticker, timestamp)
);

CREATE TABLE IF NOT EXISTS otc_metadata (
  ticker TEXT NOT NULL,
  date TEXT NOT NULL,
  otc_tier TEXT,
  caveat_emptor_flag INTEGER NOT NULL DEFAULT 0,
  expert_market_flag INTEGER NOT NULL DEFAULT 0,
  grey_market_flag INTEGER NOT NULL DEFAULT 0,
  reverse_split_flag INTEGER NOT NULL DEFAULT 0,
  dilution_flag INTEGER NOT NULL DEFAULT 0,
  shell_risk_flag INTEGER NOT NULL DEFAULT 0,
  promotion_risk_flag INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS catalysts (
  ticker TEXT NOT NULL,
  date TEXT NOT NULL,
  news_flag INTEGER NOT NULL DEFAULT 0,
  filing_flag INTEGER NOT NULL DEFAULT 0,
  social_spike_flag INTEGER NOT NULL DEFAULT 0,
  catalyst_text TEXT,
  catalyst_strength_score REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS level2_snapshots (
  ticker TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  best_bid REAL NOT NULL,
  best_ask REAL NOT NULL,
  bid_ask_spread_percent REAL NOT NULL,
  bid_depth_shares INTEGER NOT NULL,
  ask_depth_shares INTEGER NOT NULL,
  estimated_buy_fill_shares INTEGER NOT NULL,
  estimated_sell_fill_shares INTEGER NOT NULL,
  order_book_imbalance REAL NOT NULL,
  PRIMARY KEY (ticker, timestamp)
);

CREATE TABLE IF NOT EXISTS signals (
  ticker TEXT NOT NULL,
  date TEXT NOT NULL,
  timestamp TEXT,
  signal_score REAL NOT NULL,
  passed_watchlist INTEGER NOT NULL,
  passed_tradable INTEGER NOT NULL,
  reason TEXT
);

CREATE TABLE IF NOT EXISTS trades (
  trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  entry_timestamp TEXT NOT NULL,
  exit_timestamp TEXT,
  entry_price REAL NOT NULL,
  exit_price REAL,
  shares INTEGER NOT NULL,
  position_dollars REAL NOT NULL,
  realized_gain_loss REAL,
  realized_gain_loss_pct REAL,
  exit_reason TEXT
);

CREATE TABLE IF NOT EXISTS positions (
  ticker TEXT PRIMARY KEY,
  entry_timestamp TEXT NOT NULL,
  avg_cost REAL NOT NULL,
  shares INTEGER NOT NULL,
  position_dollars REAL NOT NULL,
  highest_price_since_entry REAL NOT NULL,
  breakout_day_volume INTEGER NOT NULL,
  current_status TEXT NOT NULL
);
