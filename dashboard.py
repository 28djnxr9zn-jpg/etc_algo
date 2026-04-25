from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from backtests.backtest import run_backtest_detailed
from data_providers.alpha_vantage import fetch_symbols, normalize_symbols
from data_providers.ibkr_tws import (
    IBKRConnectionConfig,
    discover_scanner_universe,
    fetch_historical_daily_prices,
    fetch_level2_snapshot,
)
from database.db import (
    DB_PATH,
    get_connection,
    get_universe_tickers,
    init_db,
    list_universes,
    load_sample_data,
    load_settings,
    read_table,
    replace_table_rows,
    upsert_universe,
)
from monitoring.intraday_monitor import run_monitor_sim
from scanners.universe import MarketFrames, scan_universe
from strategies.scoring import calculate_signal_score

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


st.set_page_config(page_title="OTC Algo Dashboard", layout="wide")


def load_frames() -> MarketFrames:
    return MarketFrames(
        prices=read_table("prices"),
        metadata=read_table("otc_metadata"),
        catalysts=read_table("catalysts"),
        level2=read_table("level2_snapshots"),
    )


def database_has_data() -> bool:
    try:
        return not read_table("prices").empty
    except Exception:
        return False


def saved_universe_names() -> list[str]:
    try:
        names = list_universes(DB_PATH)
    except Exception:
        names = []
    return names


def parse_tickers_text(text: str) -> list[str]:
    return normalize_symbols(text)


def choose_universe(label: str, key_prefix: str, default_manual: str = "AAPL,MSFT") -> tuple[str, list[str]]:
    names = saved_universe_names()
    choice = st.selectbox(label, ["Manual tickers"] + names, key=f"{key_prefix}_universe")
    if choice == "Manual tickers":
        manual_symbols = st.text_area("Manual tickers", value=default_manual, key=f"{key_prefix}_manual")
        symbols = normalize_symbols(manual_symbols)
    else:
        symbols = get_universe_tickers(choice, DB_PATH)
        st.dataframe(pd.DataFrame({"ticker": symbols}), use_container_width=True, hide_index=True)
    st.caption(f"Selected {len(symbols)} tickers.")
    return choice, symbols


def settings_from_sidebar() -> dict:
    settings = load_settings()
    st.sidebar.header("Controls")

    st.sidebar.subheader("Entry")
    settings["entry"]["min_price"] = st.sidebar.number_input(
        "Minimum entry price",
        min_value=0.0001,
        max_value=1.0,
        value=float(settings["entry"]["min_price"]),
        step=0.0001,
        format="%.4f",
    )
    settings["entry"]["max_price"] = st.sidebar.number_input(
        "Maximum entry price",
        min_value=0.0001,
        max_value=1.0,
        value=float(settings["entry"]["max_price"]),
        step=0.001,
        format="%.4f",
    )

    st.sidebar.subheader("Watchlist")
    settings["watchlist"]["min_avg_volume_20d"] = st.sidebar.number_input(
        "Min 20-day avg volume",
        min_value=0,
        value=int(settings["watchlist"]["min_avg_volume_20d"]),
        step=50_000,
    )
    settings["watchlist"]["min_avg_dollar_volume_20d"] = st.sidebar.number_input(
        "Min 20-day avg dollar volume",
        min_value=0,
        value=int(settings["watchlist"]["min_avg_dollar_volume_20d"]),
        step=100,
    )

    st.sidebar.subheader("Tradable")
    settings["tradable"]["min_volume_breakout_multiple"] = st.sidebar.slider(
        "Min volume breakout multiple",
        min_value=1.0,
        max_value=10.0,
        value=float(settings["tradable"]["min_volume_breakout_multiple"]),
        step=0.5,
    )
    settings["tradable"]["min_current_dollar_volume"] = st.sidebar.number_input(
        "Min current dollar volume",
        min_value=0,
        value=int(settings["tradable"]["min_current_dollar_volume"]),
        step=1_000,
    )
    settings["tradable"]["require_catalyst"] = st.sidebar.checkbox(
        "Require catalyst",
        value=bool(settings["tradable"]["require_catalyst"]),
        help="Turn this off for IBKR price-only data because IBKR bars do not include news/catalyst fields.",
    )
    settings["execution"]["max_spread_pct"] = st.sidebar.slider(
        "Max spread %",
        min_value=1,
        max_value=100,
        value=int(settings["execution"]["max_spread_pct"]),
        step=1,
    )

    st.sidebar.subheader("Sizing")
    settings["portfolio"]["starting_cash"] = st.sidebar.number_input(
        "Starting cash",
        min_value=100,
        value=int(settings["portfolio"]["starting_cash"]),
        step=500,
    )
    settings["sizing"]["fixed_dollar_cap_per_ticker"] = st.sidebar.number_input(
        "Fixed dollar cap per ticker",
        min_value=0,
        value=int(settings["sizing"]["fixed_dollar_cap_per_ticker"]),
        step=100,
    )
    settings["sizing"]["max_single_position_pct"] = st.sidebar.slider(
        "Max single ticker exposure %",
        min_value=1,
        max_value=25,
        value=int(settings["sizing"]["max_single_position_pct"] * 100),
        step=1,
    ) / 100

    st.sidebar.subheader("Risk Exits")
    settings["risk_exits"]["massive_drop_from_intraday_high_pct"] = st.sidebar.slider(
        "Exit drop from high %",
        min_value=5,
        max_value=90,
        value=int(settings["risk_exits"]["massive_drop_from_intraday_high_pct"]),
        step=5,
    )
    settings["risk_exits"]["massive_drop_from_last_scan_pct"] = st.sidebar.slider(
        "Exit drop from last scan %",
        min_value=5,
        max_value=90,
        value=int(settings["risk_exits"]["massive_drop_from_last_scan_pct"]),
        step=5,
    )
    settings["risk_exits"]["exit_on_price_above_entry_range"] = st.sidebar.checkbox(
        "Sell just because price rises above entry max",
        value=bool(settings["risk_exits"]["exit_on_price_above_entry_range"]),
        help="Leave this off for the intended hold-winners behavior.",
    )

    st.sidebar.subheader("Safety")
    settings["portfolio"]["global_stop_trading"] = st.sidebar.checkbox(
        "Global stop trading",
        value=bool(settings["portfolio"]["global_stop_trading"]),
    )
    settings["portfolio"]["flatten_all_positions"] = st.sidebar.checkbox(
        "Flatten all positions",
        value=bool(settings["portfolio"]["flatten_all_positions"]),
    )
    settings["portfolio"]["live_trading_enabled"] = False
    settings["portfolio"]["paper_trading_enabled"] = False
    return settings


def render_database_controls() -> None:
    st.subheader("Database")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Initialize database", use_container_width=True):
            init_db(DB_PATH)
            st.success(f"Initialized {DB_PATH}")
    with col2:
        if st.button("Load sample data", use_container_width=True):
            load_sample_data(DB_PATH)
            st.success("Loaded sample data")
    with col3:
        st.metric("Sample data loaded", "Yes" if database_has_data() else "No")


def render_universe() -> None:
    st.subheader("Universe Selection")
    st.caption("Create a saved ticker universe once, then use it for IBKR fetching, scanning, and backtesting.")

    names = saved_universe_names()
    if names:
        selected = st.selectbox("Saved universes", names)
        tickers = get_universe_tickers(selected, DB_PATH)
        st.metric("Tickers", len(tickers))
        st.dataframe(pd.DataFrame({"ticker": tickers}), use_container_width=True, hide_index=True)
    else:
        st.info("No universes saved yet. Create one below or load sample data.")

    st.divider()
    st.write("Create or replace a universe")
    universe_name = st.text_input("Universe name", value="my_scan_universe")
    tickers_text = st.text_area("Tickers", value="AAPL,MSFT,NVDA", help="Comma or newline separated.")
    uploaded = st.file_uploader("Or upload CSV with a ticker column", type=["csv"])
    source = st.text_input("Source", value="manual")
    notes = st.text_input("Notes", value="")
    if st.button("Save universe", type="primary"):
        tickers = parse_tickers_text(tickers_text)
        if uploaded is not None:
            uploaded_frame = pd.read_csv(uploaded)
            if "ticker" not in uploaded_frame.columns:
                st.error("Uploaded CSV must include a ticker column.")
                return
            tickers.extend(uploaded_frame["ticker"].dropna().astype(str).tolist())
        if not universe_name.strip():
            st.error("Add a universe name.")
            return
        if not tickers:
            st.error("Add at least one ticker.")
            return
        upsert_universe(universe_name.strip(), tickers, source=source, notes=notes, db_path=DB_PATH)
        st.success(f"Saved {len(set(tickers))} tickers to {universe_name}.")


def render_live_data(settings: dict) -> None:
    st.subheader("Live / Delayed Price Data")
    st.caption(
        "Fetches real OHLCV price history from Alpha Vantage. This does not include OTC metadata, catalysts, or Level 2 depth."
    )
    api_key = st.text_input("Alpha Vantage API key", type="password")
    symbols_text = st.text_area(
        "Tickers",
        value="AAPL,MSFT",
        help="Use symbols supported by your data provider. OTC symbols may require provider-specific formats.",
    )
    outputsize = st.selectbox("History size", ["compact", "full"], index=0)
    require_catalyst = st.checkbox(
        "Require catalyst for tradable candidates",
        value=bool(settings["tradable"]["require_catalyst"]),
        help="Price providers usually do not include catalyst data, so turn this off to test price-only scans.",
    )
    settings["tradable"]["require_catalyst"] = require_catalyst

    if st.button("Fetch and replace database prices", type="primary"):
        symbols = normalize_symbols(symbols_text)
        if not api_key:
            st.error("Add an Alpha Vantage API key first.")
            return
        if not symbols:
            st.error("Add at least one ticker.")
            return
        with st.spinner("Fetching data. Free API keys are rate-limited, so multiple tickers can take a minute."):
            result = fetch_symbols(symbols, api_key, outputsize=outputsize)
        if result.prices.empty:
            st.error("No prices loaded.")
        else:
            init_db(DB_PATH)
            replace_table_rows(result.prices, "prices", DB_PATH)
            replace_table_rows(result.metadata, "otc_metadata", DB_PATH)
            replace_table_rows(result.catalysts, "catalysts", DB_PATH)
            with get_connection(DB_PATH) as conn:
                conn.execute("DELETE FROM level2_snapshots")
            st.success(f"Loaded {len(result.prices)} price rows for {result.prices['ticker'].nunique()} symbols.")
            st.dataframe(result.prices.sort_values(["ticker", "date"], ascending=[True, False]).head(25), use_container_width=True)
        if result.errors:
            st.warning("Some symbols failed:\n\n" + "\n".join(result.errors))


def render_ibkr_data(settings: dict) -> None:
    st.subheader("IBKR TWS / Gateway Data")
    st.caption("Data-only connection. This dashboard does not place live or paper orders.")

    col1, col2, col3 = st.columns(3)
    host = col1.text_input("Host", value="127.0.0.1")
    port = col2.number_input("Port", min_value=1, max_value=65535, value=7497, help="7497 is common for TWS paper. 7496 is common for TWS live.")
    client_id = col3.number_input("Client ID", min_value=1, max_value=9999, value=7)

    col4, col5, col6 = st.columns(3)
    exchange = col4.text_input("Exchange", value="SMART")
    primary_exchange = col5.text_input("Primary exchange", value="", help="Optional. OTC/PINK symbols may need provider-specific mapping.")
    currency = col6.text_input("Currency", value="USD")

    market_data_type = st.selectbox("Market data type", ["Live", "Delayed", "Frozen", "Delayed frozen"], index=1)
    duration = st.selectbox("Historical duration", ["30 D", "60 D", "6 M", "1 Y"], index=1)
    what_to_show = st.selectbox("Historical data type", ["TRADES", "MIDPOINT", "BID", "ASK"], index=0)
    use_rth = st.checkbox("Regular trading hours only", value=False)
    config = IBKRConnectionConfig(host=host, port=int(port), client_id=int(client_id), readonly=True)

    st.info(
        "Before using this: open TWS or IB Gateway, enable API socket clients, and log into paper if you are testing. "
        "Paid market-data subscriptions control whether live quotes and Level 2 depth are returned."
    )

    discovery_tab, bars_tab, depth_tab = st.tabs(["Discover Universe", "Historical Bars", "Level 2 Snapshot"])

    with discovery_tab:
        st.write("Use IBKR/TWS market scanners to discover a candidate universe automatically.")
        st.caption(
            "Scanner coverage comes from TWS. For OTC/sub-penny names, start broad, save the results, then let the local scanner enforce price/liquidity rules."
        )
        dcol1, dcol2, dcol3 = st.columns(3)
        scan_code = dcol1.selectbox(
            "Scan code",
            ["HOT_BY_VOLUME", "TOP_PERC_GAIN", "MOST_ACTIVE", "TOP_TRADE_COUNT", "HOT_BY_PRICE"],
            index=0,
        )
        location_code = dcol2.text_input("Scanner location", value="STK.US", help="Examples: STK.US, STK.US.MAJOR, STK.US.MINOR. Availability depends on TWS.")
        max_results = dcol3.number_input("Max results", min_value=1, max_value=200, value=50, step=10)

        fcol1, fcol2, fcol3 = st.columns(3)
        scanner_min_price = fcol1.number_input("Scanner min price", min_value=0.0, value=0.0001, step=0.0001, format="%.4f")
        scanner_max_price = fcol2.number_input("Scanner max price", min_value=0.0, value=float(settings["entry"]["max_price"]), step=0.01, format="%.4f")
        scanner_min_volume = fcol3.number_input("Scanner min volume", min_value=0, value=0, step=10000)
        stock_type_filter = st.selectbox("Stock type filter", ["", "CORP", "ADR", "ETF", "REIT", "CEF"], index=0)
        discovered_universe_name = st.text_input("Save discovered universe as", value="ibkr_discovered")

        if st.button("Discover universe from IBKR scanner", type="primary"):
            with st.spinner("Requesting scanner results from TWS..."):
                discovered, errors = discover_scanner_universe(
                    config=config,
                    scan_code=scan_code,
                    location_code=location_code,
                    max_results=int(max_results),
                    min_price=scanner_min_price if scanner_min_price > 0 else None,
                    max_price=scanner_max_price if scanner_max_price > 0 else None,
                    min_volume=int(scanner_min_volume) if scanner_min_volume > 0 else None,
                    stock_type_filter=stock_type_filter,
                )
            if not discovered.empty:
                upsert_universe(
                    discovered_universe_name,
                    discovered["ticker"].dropna().astype(str).tolist(),
                    source=f"ibkr:{scan_code}:{location_code}",
                    notes="Auto-discovered through TWS market scanner",
                    db_path=DB_PATH,
                )
                st.success(f"Discovered and saved {discovered['ticker'].nunique()} symbols to {discovered_universe_name}.")
                st.dataframe(discovered, use_container_width=True, hide_index=True)
            if errors:
                st.warning("\n".join(errors))

    with bars_tab:
        _, symbols = choose_universe("Universe to fetch historical bars for", "bars")
        if st.button("Fetch IBKR historical bars into database", type="primary"):
            if not symbols:
                st.error("Add at least one ticker.")
                return
            with st.spinner("Connecting to TWS/Gateway and fetching bars..."):
                prices, errors = fetch_historical_daily_prices(
                    symbols=symbols,
                    config=config,
                    exchange=exchange,
                    primary_exchange=primary_exchange or None,
                    currency=currency,
                    duration=duration,
                    market_data_type=market_data_type,
                    what_to_show=what_to_show,
                    use_rth=use_rth,
                )
            if not prices.empty:
                init_db(DB_PATH)
                replace_table_rows(prices, "prices", DB_PATH)
                from data_providers.alpha_vantage import neutral_catalysts, neutral_metadata

                replace_table_rows(neutral_metadata(sorted(prices["ticker"].unique())), "otc_metadata", DB_PATH)
                replace_table_rows(neutral_catalysts(sorted(prices["ticker"].unique())), "catalysts", DB_PATH)
                st.success(f"Loaded {len(prices)} IBKR bar rows for {prices['ticker'].nunique()} symbols.")
                st.dataframe(prices.sort_values(["ticker", "date"], ascending=[True, False]).head(25), use_container_width=True, hide_index=True)
            if errors:
                st.warning("Some requests failed:\n\n" + "\n".join(errors))

    with depth_tab:
        st.write("Request an IBKR market-depth snapshot with `reqMktDepth`.")
        depth_symbols = saved_universe_names()
        depth_universe = st.selectbox("Optional source universe", ["Manual ticker"] + depth_symbols, key="depth_universe")
        universe_symbols = get_universe_tickers(depth_universe, DB_PATH) if depth_universe != "Manual ticker" else []
        depth_symbol = st.text_input("Depth test ticker", value=universe_symbols[0] if universe_symbols else "AAPL")
        depth_rows = st.slider("Depth rows", min_value=1, max_value=10, value=5)
        smart_depth = st.checkbox("Smart depth", value=False)
        if st.button("Test IBKR Level 2 snapshot", type="primary"):
            with st.spinner("Requesting market depth..."):
                snapshot, errors = fetch_level2_snapshot(
                    symbol=depth_symbol,
                    config=config,
                    settings=settings,
                    exchange=exchange,
                    primary_exchange=primary_exchange or None,
                    currency=currency,
                    rows=depth_rows,
                    smart_depth=smart_depth,
                    market_data_type=market_data_type,
                )
            if snapshot:
                st.success("Received Level 2 snapshot.")
                st.dataframe(pd.DataFrame([snapshot]), use_container_width=True, hide_index=True)
            if errors:
                st.warning("\n".join(errors))


def scanner_frame(settings: dict) -> pd.DataFrame:
    scan = scan_universe(load_frames(), settings)
    if scan.empty:
        return scan
    scan["signal_score"] = scan.apply(lambda row: calculate_signal_score(row, settings), axis=1)
    return scan.sort_values("signal_score", ascending=False)


def render_scanner(settings: dict) -> None:
    st.subheader("Scanner")
    try:
        scan = scanner_frame(settings)
    except Exception as exc:
        st.warning(f"No scan data yet: {exc}")
        return
    if scan.empty:
        st.info("No data found. Use the Database tab to load sample data.")
        return
    columns = [
        "ticker",
        "close",
        "volume",
        "avg_volume_20d",
        "dollar_volume",
        "passed_watchlist",
        "passed_tradable",
        "signal_score",
        "reason",
    ]
    st.dataframe(scan[columns], use_container_width=True, hide_index=True)


def render_backtest(settings: dict) -> None:
    st.subheader("Backtest")
    st.caption("Signals are generated after a daily close. Entries are simulated on the next available trading day. No live or paper orders are sent.")
    st.info(
        "For IBKR price-only data, catalyst and OTC risk fields are neutral placeholders unless you load a richer dataset. "
        "For a price-only test, turn off 'Require catalyst for tradable candidates' in the Live Data tab or loosen the sidebar thresholds."
    )
    if st.button("Run backtest", type="primary"):
        try:
            result = run_backtest_detailed(load_frames(), settings)
        except Exception as exc:
            st.error(f"Backtest failed: {exc}")
            return
        metrics = result["metrics"]
        trades = result["trades"]

        metric_cols = st.columns(4)
        metric_cols[0].metric("Portfolio value", f"${metrics['portfolio_value']:,.2f}")
        metric_cols[1].metric("Total return", f"{metrics['total_return_pct']}%")
        metric_cols[2].metric("Trades", metrics["number_of_trades"])
        metric_cols[3].metric("Open positions", metrics["positions_still_open"])

        metrics_tab, equity_tab, trades_tab, candidates_tab, rejects_tab = st.tabs(
            ["Metrics", "Equity Curve", "Trades", "Candidates", "Rejects"]
        )
        with metrics_tab:
            st.dataframe(pd.DataFrame([metrics]), use_container_width=True, hide_index=True)
        with equity_tab:
            equity = pd.DataFrame(result["equity_curve"])
            if not equity.empty:
                st.line_chart(equity.set_index("date")["portfolio_value"])
                st.dataframe(equity, use_container_width=True, hide_index=True)
        with trades_tab:
            if trades:
                st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True)
            else:
                st.info("No trades were created. Check the Candidates and Rejects tabs to see which filter blocked entries.")
        with candidates_tab:
            candidates = pd.DataFrame(result["candidate_log"])
            if not candidates.empty:
                st.dataframe(candidates.sort_values(["date", "signal_score"], ascending=[False, False]), use_container_width=True, hide_index=True)
        with rejects_tab:
            rejects = pd.DataFrame(result["rejected_orders"])
            if not rejects.empty:
                st.dataframe(rejects, use_container_width=True, hide_index=True)
            else:
                st.info("No rejected entry orders.")


def render_monitor(settings: dict) -> None:
    st.subheader("15-Minute Monitor Simulation")
    st.caption("Checks a sample open position against the latest scanner snapshot. It only recommends actions.")
    try:
        scan = scanner_frame(settings)
    except Exception as exc:
        st.warning(f"No monitor data yet: {exc}")
        return
    if scan.empty:
        st.info("Load sample data first.")
        return
    positions = [
        {
            "ticker": "ALFA",
            "entry_timestamp": "2026-01-05",
            "avg_cost": 0.003,
            "shares": 50_000,
            "highest_price_since_entry": 0.007,
            "breakout_day_volume": 7_000_000,
            "last_scan_price": 0.006,
        }
    ]
    alerts = run_monitor_sim(positions, scan, settings)
    st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)


def main() -> None:
    settings = settings_from_sidebar()
    st.title("OTC Algo Dashboard")
    st.caption("Speculative OTC/sub-penny scanner, backtester, and risk monitor. Live trading is disabled.")

    safety_cols = st.columns(3)
    safety_cols[0].metric("Live trading", "Disabled")
    safety_cols[1].metric("Paper trading", "Disabled")
    safety_cols[2].metric("Entry range", f"${settings['entry']['min_price']:.4f} - ${settings['entry']['max_price']:.4f}")

    tab_db, tab_universe, tab_live, tab_ibkr, tab_scan, tab_backtest, tab_monitor = st.tabs(["Database", "Universe", "Live Data", "IBKR", "Scanner", "Backtest", "Monitor"])
    with tab_db:
        render_database_controls()
    with tab_universe:
        render_universe()
    with tab_live:
        render_live_data(settings)
    with tab_ibkr:
        render_ibkr_data(settings)
    with tab_scan:
        render_scanner(settings)
    with tab_backtest:
        render_backtest(settings)
    with tab_monitor:
        render_monitor(settings)


if __name__ == "__main__":
    main()
