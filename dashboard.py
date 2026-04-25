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

st.set_page_config(page_title="OTC Algo", layout="wide")


def inject_design() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #070a0f;
            --panel: #0d121a;
            --panel-2: #111823;
            --panel-3: #151e2a;
            --text: #f5f7fb;
            --muted: #98a4b3;
            --line: rgba(255, 255, 255, 0.10);
            --blue: #28d7ff;
            --green: #39ff88;
            --pink: #ff3d71;
            --amber: #f7c948;
        }

        .stApp {
            background:
                radial-gradient(circle at 16% -10%, rgba(40, 215, 255, 0.14), transparent 28%),
                radial-gradient(circle at 88% 4%, rgba(57, 255, 136, 0.08), transparent 26%),
                var(--bg);
            color: var(--text);
        }

        header[data-testid="stHeader"] {
            background: rgba(7, 10, 15, 0.76);
            backdrop-filter: blur(16px);
        }

        .block-container {
            max-width: 1240px;
            padding-top: 1.25rem;
            padding-bottom: 4rem;
        }

        section[data-testid="stSidebar"] {
            background: #090d13;
            border-right: 1px solid var(--line);
        }

        h1, h2, h3, h4 {
            color: var(--text);
            letter-spacing: 0;
        }

        p, label, .stCaption, [data-testid="stMarkdownContainer"] {
            color: var(--muted);
            letter-spacing: 0;
        }

        .app-shell {
            border: 1px solid var(--line);
            border-radius: 22px;
            padding: 24px;
            background:
                linear-gradient(135deg, rgba(40, 215, 255, 0.10), rgba(57, 255, 136, 0.04) 38%, rgba(255, 61, 113, 0.06)),
                rgba(13, 18, 26, 0.86);
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.34);
            margin-bottom: 18px;
        }

        .kicker {
            color: var(--blue);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .app-title {
            color: var(--text);
            font-size: 46px;
            line-height: 1.02;
            font-weight: 760;
            max-width: 900px;
            margin-bottom: 10px;
        }

        .app-subtitle {
            color: var(--muted);
            font-size: 17px;
            line-height: 1.45;
            max-width: 780px;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 6px 10px;
            margin: 14px 7px 0 0;
            background: rgba(255, 255, 255, 0.055);
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
        }

        .badge.green { color: var(--green); background: rgba(57, 255, 136, 0.10); }
        .badge.blue { color: var(--blue); background: rgba(40, 215, 255, 0.10); }
        .badge.pink { color: var(--pink); background: rgba(255, 61, 113, 0.10); }

        .section-head {
            margin: 8px 0 18px;
            padding-bottom: 14px;
            border-bottom: 1px solid var(--line);
        }

        .section-kicker {
            color: var(--blue);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            margin-bottom: 7px;
        }

        .section-title {
            color: var(--text);
            font-size: 32px;
            font-weight: 740;
            line-height: 1.08;
        }

        .section-copy {
            color: var(--muted);
            font-size: 15px;
            line-height: 1.45;
            max-width: 820px;
            margin-top: 8px;
        }

        .panel {
            background: rgba(17, 24, 35, 0.90);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 18px 18px 16px;
            min-height: 118px;
        }

        .panel-title {
            color: var(--text);
            font-size: 17px;
            font-weight: 720;
            margin-bottom: 6px;
        }

        .panel-copy {
            color: var(--muted);
            font-size: 14px;
            line-height: 1.4;
        }

        .pipeline {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 14px 0 20px;
        }

        .step {
            border: 1px solid var(--line);
            background: rgba(255, 255, 255, 0.045);
            border-radius: 14px;
            padding: 14px;
        }

        .step-num {
            color: var(--green);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.12em;
            margin-bottom: 8px;
        }

        .step-title {
            color: var(--text);
            font-size: 15px;
            font-weight: 720;
            margin-bottom: 4px;
        }

        .step-copy {
            color: var(--muted);
            font-size: 13px;
            line-height: 1.35;
        }

        div[data-testid="stMetric"] {
            background: rgba(17, 24, 35, 0.92);
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 16px 18px;
        }

        div[data-testid="stMetricLabel"] p {
            color: var(--muted);
            font-size: 12px;
            font-weight: 700;
        }

        div[data-testid="stMetricValue"] {
            color: var(--text);
            font-weight: 740;
        }

        .stButton > button {
            border-radius: 12px;
            border: 1px solid var(--line);
            background: #111823;
            color: var(--text);
            font-weight: 720;
            min-height: 42px;
        }

        .stButton > button[kind="primary"] {
            color: #061014;
            border-color: rgba(255,255,255,0.20);
            background: linear-gradient(135deg, var(--blue), var(--green));
        }

        div[role="radiogroup"] label {
            border: 1px solid var(--line);
            border-radius: 12px;
            background: rgba(255,255,255,0.04);
            padding: 8px 10px;
            margin-bottom: 6px;
        }

        .stTabs [data-baseweb="tab-list"] {
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 6px;
            gap: 6px;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 10px;
            color: var(--muted);
            font-weight: 700;
        }

        .stTabs [aria-selected="true"] {
            color: var(--text);
            background: rgba(40, 215, 255, 0.18);
        }

        .stDataFrame, div[data-testid="stTable"] {
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid var(--line);
        }

        div[data-testid="stAlert"] {
            border-radius: 14px;
            border: 1px solid var(--line);
        }

        input, textarea, div[data-baseweb="select"] > div {
            border-radius: 10px !important;
        }

        hr { border-color: var(--line); }

        @media (max-width: 880px) {
            .app-title { font-size: 34px; }
            .pipeline { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def html_panel(title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="panel">
            <div class="panel-title">{title}</div>
            <div class="panel-copy">{copy}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(kicker: str, title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="section-head">
            <div class="section-kicker">{kicker}</div>
            <div class="section-title">{title}</div>
            <div class="section-copy">{copy}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def app_hero(settings: dict) -> None:
    st.markdown(
        f"""
        <div class="app-shell">
            <div class="kicker">OTC Algo</div>
            <div class="app-title">Autonomous OTC research, kept on a leash.</div>
            <div class="app-subtitle">
                Discover symbols through IBKR, refresh bars, scan for tradable setups,
                and run a liquidity-aware backtest without enabling live orders.
            </div>
            <span class="badge green">Live trading off</span>
            <span class="badge pink">Paper orders off</span>
            <span class="badge blue">Entry ${settings['entry']['min_price']:.4f} to ${settings['entry']['max_price']:.4f}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def pipeline_strip() -> None:
    st.markdown(
        """
        <div class="pipeline">
            <div class="step"><div class="step-num">01</div><div class="step-title">Discover</div><div class="step-copy">Use IBKR scanner results to create a universe automatically.</div></div>
            <div class="step"><div class="step-num">02</div><div class="step-title">Refresh</div><div class="step-copy">Fetch historical bars from TWS or IB Gateway.</div></div>
            <div class="step"><div class="step-num">03</div><div class="step-title">Score</div><div class="step-copy">Apply price, volume, liquidity, and risk filters.</div></div>
            <div class="step"><div class="step-num">04</div><div class="step-title">Backtest</div><div class="step-copy">Simulate next-day entries, partial fills, and risk exits.</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def load_frames() -> MarketFrames:
    return MarketFrames(
        prices=read_table("prices"),
        metadata=read_table("otc_metadata"),
        catalysts=read_table("catalysts"),
        level2=read_table("level2_snapshots"),
    )


def read_optional_table(table: str) -> pd.DataFrame:
    try:
        return read_table(table)
    except Exception:
        return pd.DataFrame()


def data_health() -> dict:
    prices = read_optional_table("prices")
    signals = read_optional_table("signals")
    return {
        "database_ready": not prices.empty,
        "price_rows": len(prices),
        "symbols": prices["ticker"].nunique() if not prices.empty and "ticker" in prices else 0,
        "last_date": prices["date"].max() if not prices.empty and "date" in prices else "No data",
        "universes": len(saved_universe_names()),
        "signals": len(signals),
    }


def saved_universe_names() -> list[str]:
    try:
        return list_universes(DB_PATH)
    except Exception:
        return []


def choose_universe(label: str, key_prefix: str, default_manual: str = "AAPL,MSFT") -> tuple[str, list[str]]:
    names = saved_universe_names()
    choice = st.selectbox(label, ["Manual tickers"] + names, key=f"{key_prefix}_universe")
    if choice == "Manual tickers":
        symbols = normalize_symbols(st.text_area("Manual tickers", value=default_manual, key=f"{key_prefix}_manual"))
    else:
        symbols = get_universe_tickers(choice, DB_PATH)
        with st.expander(f"View {len(symbols)} symbols", expanded=False):
            st.dataframe(pd.DataFrame({"ticker": symbols}), use_container_width=True, hide_index=True)
    st.caption(f"{len(symbols)} symbols selected")
    return choice, symbols


def build_settings() -> tuple[str, dict]:
    settings = load_settings()
    st.sidebar.title("OTC Algo")
    st.sidebar.caption("Research cockpit")
    page = st.sidebar.radio(
        "Navigate",
        ["Command Center", "Autopilot", "Data", "Research", "Universe", "Risk & Admin"],
        index=0,
    )

    with st.sidebar.expander("Strategy Settings", expanded=False):
        st.caption("Entry")
        settings["entry"]["min_price"] = st.number_input(
            "Minimum entry price", min_value=0.0001, max_value=1.0, value=float(settings["entry"]["min_price"]), step=0.0001, format="%.4f"
        )
        settings["entry"]["max_price"] = st.number_input(
            "Maximum entry price", min_value=0.0001, max_value=1.0, value=float(settings["entry"]["max_price"]), step=0.001, format="%.4f"
        )

        st.caption("Liquidity")
        settings["watchlist"]["min_avg_volume_20d"] = st.number_input(
            "Min 20-day avg volume", min_value=0, value=int(settings["watchlist"]["min_avg_volume_20d"]), step=50_000
        )
        settings["watchlist"]["min_avg_dollar_volume_20d"] = st.number_input(
            "Min 20-day avg dollar volume", min_value=0, value=int(settings["watchlist"]["min_avg_dollar_volume_20d"]), step=100
        )
        settings["tradable"]["min_volume_breakout_multiple"] = st.slider(
            "Volume breakout multiple", min_value=1.0, max_value=10.0, value=float(settings["tradable"]["min_volume_breakout_multiple"]), step=0.5
        )
        settings["tradable"]["min_current_dollar_volume"] = st.number_input(
            "Min current dollar volume", min_value=0, value=int(settings["tradable"]["min_current_dollar_volume"]), step=1_000
        )
        settings["tradable"]["require_catalyst"] = st.checkbox(
            "Require catalyst", value=bool(settings["tradable"]["require_catalyst"]), help="Turn off for IBKR price-only data."
        )
        settings["execution"]["max_spread_pct"] = st.slider(
            "Max spread %", min_value=1, max_value=100, value=int(settings["execution"]["max_spread_pct"]), step=1
        )

        st.caption("Sizing")
        settings["portfolio"]["starting_cash"] = st.number_input(
            "Starting cash", min_value=100, value=int(settings["portfolio"]["starting_cash"]), step=500
        )
        settings["sizing"]["fixed_dollar_cap_per_ticker"] = st.number_input(
            "Fixed dollar cap", min_value=0, value=int(settings["sizing"]["fixed_dollar_cap_per_ticker"]), step=100
        )
        settings["sizing"]["max_single_position_pct"] = st.slider(
            "Max single ticker %", min_value=1, max_value=25, value=int(settings["sizing"]["max_single_position_pct"] * 100), step=1
        ) / 100

        st.caption("Risk")
        settings["risk_exits"]["massive_drop_from_intraday_high_pct"] = st.slider(
            "Drop from high exit %", min_value=5, max_value=90, value=int(settings["risk_exits"]["massive_drop_from_intraday_high_pct"]), step=5
        )
        settings["risk_exits"]["massive_drop_from_last_scan_pct"] = st.slider(
            "Drop from scan exit %", min_value=5, max_value=90, value=int(settings["risk_exits"]["massive_drop_from_last_scan_pct"]), step=5
        )
        settings["risk_exits"]["exit_on_price_above_entry_range"] = st.checkbox(
            "Exit above entry max", value=bool(settings["risk_exits"]["exit_on_price_above_entry_range"])
        )

    settings["portfolio"]["live_trading_enabled"] = False
    settings["portfolio"]["paper_trading_enabled"] = False
    return page, settings


def ibkr_config(prefix: str, default_client_id: int) -> IBKRConnectionConfig:
    col1, col2, col3 = st.columns(3)
    host = col1.text_input("Host", value="127.0.0.1", key=f"{prefix}_host")
    port = col2.number_input("Port", min_value=1, max_value=65535, value=7497, key=f"{prefix}_port")
    client_id = col3.number_input("Client ID", min_value=1, max_value=9999, value=default_client_id, key=f"{prefix}_client")
    return IBKRConnectionConfig(host=host, port=int(port), client_id=int(client_id), readonly=True)


def run_autonomous_pipeline(
    settings: dict,
    config: IBKRConnectionConfig,
    scan_code: str,
    location_code: str,
    max_results: int,
    min_price: float,
    max_price: float,
    min_volume: int,
    universe_name: str,
    duration: str,
    market_data_type: str,
    what_to_show: str,
    use_rth: bool,
) -> dict:
    discovered, discovery_errors = discover_scanner_universe(
        config=config,
        scan_code=scan_code,
        location_code=location_code,
        max_results=max_results,
        min_price=min_price if min_price > 0 else None,
        max_price=max_price if max_price > 0 else None,
        min_volume=min_volume if min_volume > 0 else None,
        stock_type_filter="",
    )
    tickers = discovered["ticker"].dropna().astype(str).tolist() if not discovered.empty else []
    if tickers:
        upsert_universe(universe_name, tickers, source=f"ibkr:{scan_code}:{location_code}", notes="Autopilot discovery", db_path=DB_PATH)

    prices = pd.DataFrame()
    fetch_errors: list[str] = []
    if tickers:
        prices, fetch_errors = fetch_historical_daily_prices(
            symbols=tickers,
            config=config,
            exchange="SMART",
            primary_exchange=None,
            currency="USD",
            duration=duration,
            market_data_type=market_data_type,
            what_to_show=what_to_show,
            use_rth=use_rth,
        )
        if not prices.empty:
            init_db(DB_PATH)
            replace_table_rows(prices, "prices", DB_PATH)
            from data_providers.alpha_vantage import neutral_catalysts, neutral_metadata

            loaded_symbols = sorted(prices["ticker"].unique())
            replace_table_rows(neutral_metadata(loaded_symbols), "otc_metadata", DB_PATH)
            replace_table_rows(neutral_catalysts(loaded_symbols), "catalysts", DB_PATH)

    backtest_result = None
    if not prices.empty:
        pipeline_settings = settings.copy()
        pipeline_settings["tradable"] = settings["tradable"].copy()
        pipeline_settings["tradable"]["require_catalyst"] = False
        backtest_result = run_backtest_detailed(load_frames(), pipeline_settings)

    return {
        "discovered": discovered,
        "discovery_errors": discovery_errors,
        "prices": prices,
        "fetch_errors": fetch_errors,
        "backtest": backtest_result,
        "universe_name": universe_name,
    }


def render_pipeline_result(result: dict) -> None:
    discovered = result["discovered"]
    prices = result["prices"]
    backtest = result["backtest"]

    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Discovered", 0 if discovered.empty else discovered["ticker"].nunique())
    col2.metric("Price rows", len(prices))
    col3.metric("Symbols loaded", 0 if prices.empty else prices["ticker"].nunique())
    col4.metric("Trades", 0 if not backtest else backtest["metrics"]["number_of_trades"])

    if result["discovery_errors"]:
        st.warning("Discovery messages:\n\n" + "\n".join(result["discovery_errors"]))
    if result["fetch_errors"]:
        st.warning("Fetch messages:\n\n" + "\n".join(result["fetch_errors"]))

    tabs = st.tabs(["Universe", "Prices", "Backtest"])
    with tabs[0]:
        if discovered.empty:
            st.info("No symbols discovered.")
        else:
            st.dataframe(discovered, use_container_width=True, hide_index=True)
    with tabs[1]:
        if prices.empty:
            st.info("No price rows loaded.")
        else:
            st.dataframe(prices.sort_values(["ticker", "date"], ascending=[True, False]).head(150), use_container_width=True, hide_index=True)
    with tabs[2]:
        if not backtest:
            st.info("Backtest did not run because no prices were loaded.")
            return
        st.dataframe(pd.DataFrame([backtest["metrics"]]), use_container_width=True, hide_index=True)
        equity = pd.DataFrame(backtest["equity_curve"])
        if not equity.empty:
            st.line_chart(equity.set_index("date")["portfolio_value"])
        trades = pd.DataFrame(backtest["trades"])
        if not trades.empty:
            st.dataframe(trades, use_container_width=True, hide_index=True)


def render_command_center(settings: dict) -> None:
    app_hero(settings)
    health = data_health()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Database", "Ready" if health["database_ready"] else "Empty")
    col2.metric("Symbols", health["symbols"])
    col3.metric("Last bar", health["last_date"])
    col4.metric("Universes", health["universes"])

    st.write("")
    left, right = st.columns([1.25, 0.75])
    with left:
        page_header("Primary Workflow", "Run the autonomous research loop.", "This is the clean path: IBKR discovery, bar refresh, scan, and backtest.")
        pipeline_strip()
        if st.button("Go to Autopilot", type="primary", use_container_width=True):
            st.session_state["nav_hint"] = "Autopilot"
            st.info("Use the sidebar to open Autopilot. Streamlit navigation state is manual for now.")
    with right:
        page_header("Guardrails", "Hard safety boundaries.", "The app can research and simulate, but it cannot place orders.")
        html_panel("Trading disabled", "Live trading and paper order placement are both forced off in code.")
        st.write("")
        html_panel("IBKR is data-only", "TWS/Gateway is used for scanner and market data requests.")


def render_autopilot(settings: dict) -> None:
    page_header("Autopilot", "One-button research run.", "Use sensible defaults, then run discovery, data refresh, and backtest as a single pipeline.")
    st.warning("Research-only mode. No live or paper orders are sent.")

    config = ibkr_config("auto", default_client_id=17)
    with st.form("autopilot_form"):
        col1, col2, col3 = st.columns(3)
        scan_code = col1.selectbox("Scanner", ["HOT_BY_VOLUME", "TOP_PERC_GAIN", "MOST_ACTIVE", "TOP_TRADE_COUNT", "HOT_BY_PRICE"])
        location_code = col2.text_input("Location", value="STK.US")
        max_results = col3.number_input("Max symbols", min_value=1, max_value=200, value=50, step=10)

        col4, col5, col6 = st.columns(3)
        min_price = col4.number_input("Min price", min_value=0.0, value=float(settings["entry"]["min_price"]), step=0.0001, format="%.4f")
        max_price = col5.number_input("Max price", min_value=0.0, value=float(settings["entry"]["max_price"]), step=0.01, format="%.4f")
        min_volume = col6.number_input("Min volume", min_value=0, value=0, step=10000)

        col7, col8, col9, col10 = st.columns(4)
        universe_name = col7.text_input("Universe name", value="autopilot_ibkr")
        duration = col8.selectbox("History", ["30 D", "60 D", "6 M", "1 Y"], index=1)
        market_data_type = col9.selectbox("Data mode", ["Live", "Delayed", "Frozen", "Delayed frozen"], index=1)
        what_to_show = col10.selectbox("Bars", ["TRADES", "MIDPOINT", "BID", "ASK"], index=0)
        use_rth = st.checkbox("Regular trading hours only", value=False)
        submitted = st.form_submit_button("Run Autopilot", type="primary", use_container_width=True)

    if submitted:
        with st.spinner("Running autonomous research pipeline..."):
            st.session_state["last_pipeline"] = run_autonomous_pipeline(
                settings=settings,
                config=config,
                scan_code=scan_code,
                location_code=location_code,
                max_results=int(max_results),
                min_price=float(min_price),
                max_price=float(max_price),
                min_volume=int(min_volume),
                universe_name=universe_name,
                duration=duration,
                market_data_type=market_data_type,
                what_to_show=what_to_show,
                use_rth=use_rth,
            )

    if "last_pipeline" in st.session_state:
        render_pipeline_result(st.session_state["last_pipeline"])


def render_data(settings: dict) -> None:
    page_header("Data", "Build and refresh the research database.", "Use IBKR as the primary source. Alpha Vantage remains a fallback.")
    mode = st.radio("Data tool", ["IBKR Discover", "IBKR Historical Bars", "Alpha Vantage", "Level 2 Test"], horizontal=True)

    if mode == "IBKR Discover":
        config = ibkr_config("discover", default_client_id=27)
        col1, col2, col3 = st.columns(3)
        scan_code = col1.selectbox("Scanner", ["HOT_BY_VOLUME", "TOP_PERC_GAIN", "MOST_ACTIVE", "TOP_TRADE_COUNT", "HOT_BY_PRICE"], key="disc_scan")
        location_code = col2.text_input("Location", value="STK.US", key="disc_location")
        max_results = col3.number_input("Max results", min_value=1, max_value=200, value=50, step=10, key="disc_max")
        col4, col5, col6 = st.columns(3)
        min_price = col4.number_input("Min price", min_value=0.0, value=float(settings["entry"]["min_price"]), step=0.0001, format="%.4f", key="disc_min_price")
        max_price = col5.number_input("Max price", min_value=0.0, value=float(settings["entry"]["max_price"]), step=0.01, format="%.4f", key="disc_max_price")
        min_volume = col6.number_input("Min volume", min_value=0, value=0, step=10000, key="disc_min_vol")
        universe_name = st.text_input("Save as universe", value="ibkr_discovered")
        if st.button("Discover and Save Universe", type="primary"):
            with st.spinner("Requesting IBKR scanner results..."):
                discovered, errors = discover_scanner_universe(
                    config=config,
                    scan_code=scan_code,
                    location_code=location_code,
                    max_results=int(max_results),
                    min_price=min_price if min_price > 0 else None,
                    max_price=max_price if max_price > 0 else None,
                    min_volume=int(min_volume) if min_volume > 0 else None,
                    stock_type_filter="",
                )
            if not discovered.empty:
                upsert_universe(universe_name, discovered["ticker"].dropna().astype(str).tolist(), source=f"ibkr:{scan_code}:{location_code}", db_path=DB_PATH)
                st.success(f"Saved {discovered['ticker'].nunique()} symbols to {universe_name}.")
                st.dataframe(discovered, use_container_width=True, hide_index=True)
            if errors:
                st.warning("\n".join(errors))

    elif mode == "IBKR Historical Bars":
        config = ibkr_config("bars", default_client_id=37)
        _, symbols = choose_universe("Universe to refresh", "bars")
        col1, col2, col3, col4 = st.columns(4)
        duration = col1.selectbox("History", ["30 D", "60 D", "6 M", "1 Y"], index=1, key="bars_duration")
        market_data_type = col2.selectbox("Data mode", ["Live", "Delayed", "Frozen", "Delayed frozen"], index=1, key="bars_mode")
        what_to_show = col3.selectbox("Bars", ["TRADES", "MIDPOINT", "BID", "ASK"], index=0, key="bars_show")
        use_rth = col4.checkbox("RTH only", value=False, key="bars_rth")
        if st.button("Fetch Historical Bars", type="primary"):
            if not symbols:
                st.error("Select or enter symbols first.")
            else:
                with st.spinner("Fetching IBKR historical bars..."):
                    prices, errors = fetch_historical_daily_prices(
                        symbols=symbols,
                        config=config,
                        exchange="SMART",
                        primary_exchange=None,
                        currency="USD",
                        duration=duration,
                        market_data_type=market_data_type,
                        what_to_show=what_to_show,
                        use_rth=use_rth,
                    )
                if not prices.empty:
                    init_db(DB_PATH)
                    replace_table_rows(prices, "prices", DB_PATH)
                    from data_providers.alpha_vantage import neutral_catalysts, neutral_metadata

                    loaded = sorted(prices["ticker"].unique())
                    replace_table_rows(neutral_metadata(loaded), "otc_metadata", DB_PATH)
                    replace_table_rows(neutral_catalysts(loaded), "catalysts", DB_PATH)
                    st.success(f"Loaded {len(prices)} rows for {prices['ticker'].nunique()} symbols.")
                    st.dataframe(prices.sort_values(["ticker", "date"], ascending=[True, False]).head(100), use_container_width=True, hide_index=True)
                if errors:
                    st.warning("Some requests failed:\n\n" + "\n".join(errors))

    elif mode == "Alpha Vantage":
        api_key = st.text_input("Alpha Vantage API key", type="password")
        symbols_text = st.text_area("Tickers", value="AAPL,MSFT")
        outputsize = st.selectbox("History size", ["compact", "full"], index=0)
        if st.button("Fetch Alpha Vantage Prices", type="primary"):
            symbols = normalize_symbols(symbols_text)
            if not api_key:
                st.error("Add an API key.")
            elif not symbols:
                st.error("Add tickers.")
            else:
                with st.spinner("Fetching Alpha Vantage data..."):
                    result = fetch_symbols(symbols, api_key, outputsize=outputsize)
                if not result.prices.empty:
                    init_db(DB_PATH)
                    replace_table_rows(result.prices, "prices", DB_PATH)
                    replace_table_rows(result.metadata, "otc_metadata", DB_PATH)
                    replace_table_rows(result.catalysts, "catalysts", DB_PATH)
                    with get_connection(DB_PATH) as conn:
                        conn.execute("DELETE FROM level2_snapshots")
                    st.success(f"Loaded {len(result.prices)} rows.")
                    st.dataframe(result.prices.head(100), use_container_width=True, hide_index=True)
                if result.errors:
                    st.warning("\n".join(result.errors))

    elif mode == "Level 2 Test":
        config = ibkr_config("l2", default_client_id=47)
        symbol = st.text_input("Ticker", value="AAPL")
        col1, col2, col3 = st.columns(3)
        rows = col1.slider("Depth rows", min_value=1, max_value=10, value=5)
        smart_depth = col2.checkbox("Smart depth", value=False)
        market_data_type = col3.selectbox("Data mode", ["Live", "Delayed", "Frozen", "Delayed frozen"], index=1, key="l2_mode")
        if st.button("Test Level 2 Snapshot", type="primary"):
            with st.spinner("Requesting market depth..."):
                snapshot, errors = fetch_level2_snapshot(
                    symbol=symbol,
                    config=config,
                    settings=settings,
                    exchange="SMART",
                    primary_exchange=None,
                    currency="USD",
                    rows=rows,
                    smart_depth=smart_depth,
                    market_data_type=market_data_type,
                )
            if snapshot:
                st.dataframe(pd.DataFrame([snapshot]), use_container_width=True, hide_index=True)
            if errors:
                st.warning("\n".join(errors))


def scanner_frame(settings: dict) -> pd.DataFrame:
    scan = scan_universe(load_frames(), settings)
    if scan.empty:
        return scan
    scan["signal_score"] = scan.apply(lambda row: calculate_signal_score(row, settings), axis=1)
    return scan.sort_values("signal_score", ascending=False)


def render_research(settings: dict) -> None:
    page_header("Research", "Inspect candidates and test strategy behavior.", "Use Scanner for current candidates and Backtest for historical simulation.")
    mode = st.radio("Research mode", ["Scanner", "Backtest"], horizontal=True)
    if mode == "Scanner":
        try:
            scan = scanner_frame(settings)
        except Exception as exc:
            st.warning(f"No scan data yet: {exc}")
            return
        if scan.empty:
            st.info("No data loaded.")
            return
        columns = ["ticker", "close", "volume", "avg_volume_20d", "dollar_volume", "passed_watchlist", "passed_tradable", "signal_score", "reason"]
        st.dataframe(scan[columns], use_container_width=True, hide_index=True)
    else:
        st.info("Signals are generated after the close. Entries are simulated on the next available trading day.")
        if st.button("Run Backtest", type="primary"):
            try:
                result = run_backtest_detailed(load_frames(), settings)
            except Exception as exc:
                st.error(f"Backtest failed: {exc}")
                return
            metrics = result["metrics"]
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Portfolio value", f"${metrics['portfolio_value']:,.2f}")
            col2.metric("Return", f"{metrics['total_return_pct']}%")
            col3.metric("Trades", metrics["number_of_trades"])
            col4.metric("Open positions", metrics["positions_still_open"])

            tabs = st.tabs(["Metrics", "Equity", "Trades", "Candidates", "Rejects"])
            with tabs[0]:
                st.dataframe(pd.DataFrame([metrics]), use_container_width=True, hide_index=True)
            with tabs[1]:
                equity = pd.DataFrame(result["equity_curve"])
                if not equity.empty:
                    st.line_chart(equity.set_index("date")["portfolio_value"])
                    st.dataframe(equity, use_container_width=True, hide_index=True)
            with tabs[2]:
                trades = pd.DataFrame(result["trades"])
                if trades.empty:
                    st.info("No trades. Check Candidates and Rejects.")
                else:
                    st.dataframe(trades, use_container_width=True, hide_index=True)
            with tabs[3]:
                candidates = pd.DataFrame(result["candidate_log"])
                if not candidates.empty:
                    st.dataframe(candidates.sort_values(["date", "signal_score"], ascending=[False, False]), use_container_width=True, hide_index=True)
            with tabs[4]:
                rejects = pd.DataFrame(result["rejected_orders"])
                if rejects.empty:
                    st.info("No rejected entry orders.")
                else:
                    st.dataframe(rejects, use_container_width=True, hide_index=True)


def render_universe() -> None:
    page_header("Universe", "Saved symbol sets.", "Review scanner output or import a controlled list when you want deterministic research.")
    names = saved_universe_names()
    left, right = st.columns([0.9, 1.1])
    with left:
        if names:
            selected = st.selectbox("Saved universes", names)
            tickers = get_universe_tickers(selected, DB_PATH)
            st.metric("Tickers", len(tickers))
            st.dataframe(pd.DataFrame({"ticker": tickers}), use_container_width=True, hide_index=True)
        else:
            st.info("No universes saved yet.")
    with right:
        st.subheader("Create or Replace")
        universe_name = st.text_input("Universe name", value="my_scan_universe")
        tickers_text = st.text_area("Tickers", value="AAPL,MSFT,NVDA")
        uploaded = st.file_uploader("Upload CSV with ticker column", type=["csv"])
        source = st.text_input("Source", value="manual")
        notes = st.text_input("Notes", value="")
        if st.button("Save Universe", type="primary"):
            tickers = normalize_symbols(tickers_text)
            if uploaded is not None:
                frame = pd.read_csv(uploaded)
                if "ticker" not in frame.columns:
                    st.error("CSV must include a ticker column.")
                    return
                tickers.extend(frame["ticker"].dropna().astype(str).tolist())
            if not tickers:
                st.error("Add at least one ticker.")
                return
            upsert_universe(universe_name.strip(), tickers, source=source, notes=notes, db_path=DB_PATH)
            st.success(f"Saved {len(set(tickers))} tickers to {universe_name}.")


def render_risk_admin(settings: dict) -> None:
    page_header("Risk & Admin", "Operational checks and local setup.", "Initialize the database, load demo data, and run the monitor simulation.")
    admin, monitor = st.columns([0.9, 1.1])
    with admin:
        st.subheader("Database")
        if st.button("Initialize Database", use_container_width=True):
            init_db(DB_PATH)
            st.success(f"Initialized {DB_PATH}")
        if st.button("Load Sample Data", use_container_width=True):
            load_sample_data(DB_PATH)
            st.success("Loaded sample data.")
        health = data_health()
        st.metric("Rows", health["price_rows"])
        st.metric("Symbols", health["symbols"])
    with monitor:
        st.subheader("15-Minute Monitor Simulation")
        try:
            scan = scanner_frame(settings)
        except Exception as exc:
            st.warning(f"No monitor data yet: {exc}")
            return
        if scan.empty:
            st.info("Load data first.")
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
    inject_design()
    page, settings = build_settings()
    if page == "Command Center":
        render_command_center(settings)
    elif page == "Autopilot":
        render_autopilot(settings)
    elif page == "Data":
        render_data(settings)
    elif page == "Research":
        render_research(settings)
    elif page == "Universe":
        render_universe()
    elif page == "Risk & Admin":
        render_risk_admin(settings)


if __name__ == "__main__":
    main()
