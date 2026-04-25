# otc_algo

`otc_algo` is a beginner-friendly local Python project for scanning and backtesting speculative OTC and sub-penny stock ideas. It is built for discipline around a very high-risk, gambling-like market: liquidity checks, Level 2-aware fill simulation, position caps, and configurable risk exits are part of the MVP.

Live trading is disabled. Do not use this with real money. The IBKR module is only a placeholder for future paper trading through Trader Workstation or IB Gateway.

## What It Does

- Finds OTC/sub-penny stocks with entry prices from `$0.0001` to `$0.05`
- Applies watchlist and tradable-candidate filters
- Scores candidates from 0 to 100
- Sizes positions using portfolio, volume, and dollar-volume caps
- Simulates limit orders, partial fills, spread checks, and liquidity rejection
- Backtests a hold-biased strategy
- Monitors open positions every 15 minutes in simulation
- Keeps winners by default instead of selling just because price rises above `$0.05`

## Setup

From the `otc_algo` folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Initialize The Database

```bash
python main.py init-db
```

## Load Sample Data

```bash
python main.py load-sample-data
```

This loads fake prices, metadata, catalysts, and Level 2 snapshots into SQLite.

## Run The Scanner

```bash
python main.py scan
```

The scanner prints each ticker, filter status, score, and reason.

## Run A Backtest

```bash
python main.py backtest
```

The backtester loops through historical dates, ranks tradable candidates, simulates liquidity-aware limit-order fills, applies risk exits, and prints metrics.

## Run The Dashboard

```bash
streamlit run dashboard.py
```

The dashboard lets you initialize the database, load sample data, run the scanner, adjust key thresholds, run a backtest, inspect trades, and simulate the 15-minute monitor. The controls are local only and do not enable live or paper trading.

## Pull Real Price Data

The dashboard has a **Live Data** tab that can fetch real OHLCV price history from Alpha Vantage when you provide an API key. This replaces the local `prices`, `otc_metadata`, and `catalysts` tables with fetched price data plus neutral placeholder metadata/catalysts.

Important limitations:

- Price APIs do not automatically provide OTC caveat flags, dilution flags, promotion risk, or catalysts.
- Alpha Vantage free keys are rate-limited, so several tickers can take a minute.
- True Level 2 order-book depth is not available from this price fetch. Future Level 2 should come from IBKR TWS/Gateway `reqMktDepth` or a dedicated market-data provider.

## Run The 15-Minute Monitor Simulation

```bash
python main.py monitor-sim
```

The monitor checks open positions, logs observations, and recommends simulated exits when risk rules trigger. It does not send live orders.

## Level 2 Monitoring

Level 2 means order-book or market-depth information: best bid, best ask, displayed bid depth, displayed ask depth, spread, and estimated executable shares. OTC names can look profitable on last price while being nearly impossible to sell. This project treats Level 2 liquidity as a key safety check.

## Future IBKR Paper Trading

The intended future connection is:

```text
Python app -> Trader Workstation or IB Gateway -> IBKR paper account
```

IBKR's TWS API can request market data, send paper orders, and request market depth with `reqMktDepth`. In this MVP, `broker/ibkr.py` refuses to place real orders and returns placeholder responses.

## Tests

```bash
pytest
```

The tests cover price filters, watchlist/tradable logic, scoring, sizing, Level 2 fill estimation, partial fills, risk exits, backtest trade creation, and portfolio guardrails.
