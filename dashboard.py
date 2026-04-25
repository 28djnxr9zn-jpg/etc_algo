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
            --bg: #050505;
            --panel: #0b0b0b;
            --panel-2: #111111;
            --panel-3: #191919;
            --text: #f3f0e8;
            --muted: #aaa39a;
            --line: rgba(243, 240, 232, 0.16);
            --red: #e30613;
            --cream: #f3f0e8;
            --dark-red: #83000a;
            --warm-gray: #aaa39a;
        }

        .stApp {
            background:
                radial-gradient(circle at 16% -10%, rgba(227, 6, 19, 0.18), transparent 28%),
                radial-gradient(circle at 88% 4%, rgba(243, 240, 232, 0.06), transparent 26%),
                var(--bg);
            color: var(--text);
        }

        header[data-testid="stHeader"] {
            background: rgba(5, 5, 5, 0.84);
            backdrop-filter: blur(16px);
        }

        .block-container {
            max-width: 1240px;
            padding-top: 1.25rem;
            padding-bottom: 4rem;
        }

        section[data-testid="stSidebar"] {
            background: #080808;
            border-right: 1px solid var(--line);
        }

        .top-nav-shell {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border: 1px solid var(--line);
            background: rgba(8, 8, 8, 0.92);
            padding: 14px 18px;
            margin-bottom: 12px;
        }

        .top-nav-title {
            color: var(--text);
            text-transform: uppercase;
            letter-spacing: 0.10em;
            font-size: 13px;
            font-weight: 850;
        }

        .top-nav-meta {
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.10em;
            font-size: 11px;
            font-weight: 760;
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
            padding: 0;
            background:
                linear-gradient(100deg, rgba(0, 0, 0, 0.82), rgba(0, 0, 0, 0.40)),
                linear-gradient(135deg, rgba(227, 6, 19, 0.28), rgba(243, 240, 232, 0.08) 38%, rgba(131, 0, 10, 0.24)),
                rgba(8, 8, 8, 0.92);
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.34);
            margin-bottom: 18px;
            overflow: hidden;
            position: relative;
            min-height: 560px;
        }

        .app-shell::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
            background-size: 54px 54px;
            mask-image: linear-gradient(90deg, rgba(0,0,0,0.7), transparent 78%);
            pointer-events: none;
        }

        .site-nav {
            position: relative;
            z-index: 1;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 18px 22px;
            border-bottom: 1px solid var(--line);
            background: rgba(0,0,0,0.24);
        }

        .brand {
            color: var(--text);
            font-weight: 850;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-size: 14px;
        }

        .nav-items {
            display: flex;
            gap: 22px;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.10em;
            font-size: 11px;
            font-weight: 760;
        }

        .hero-content {
            position: relative;
            z-index: 1;
            padding: 88px 46px 44px;
            max-width: 860px;
        }

        .kicker {
            color: var(--red);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .app-title {
            color: var(--text);
            font-size: 76px;
            line-height: 0.94;
            font-weight: 860;
            max-width: 860px;
            margin-bottom: 18px;
            letter-spacing: -0.02em;
        }

        .app-subtitle {
            color: var(--muted);
            font-size: 20px;
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

        .badge.green { color: var(--cream); background: rgba(243, 240, 232, 0.10); }
        .badge.blue { color: var(--red); background: rgba(227, 6, 19, 0.14); }
        .badge.pink { color: var(--dark-red); background: rgba(131, 0, 10, 0.24); }

        .section-head {
            margin: 8px 0 18px;
            padding-bottom: 14px;
            border-bottom: 1px solid var(--line);
        }

        .section-kicker {
            color: var(--red);
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
            background: rgba(15, 15, 15, 0.94);
            border: 1px solid var(--line);
            border-radius: 0;
            padding: 22px 22px 20px;
            min-height: 142px;
            position: relative;
            overflow: hidden;
        }

        .panel::after {
            content: "";
            position: absolute;
            left: 0;
            right: 0;
            bottom: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--red), transparent);
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
            gap: 0;
            margin: 18px 0 24px;
            border: 1px solid var(--line);
        }

        .step {
            border-right: 1px solid var(--line);
            background: rgba(255, 255, 255, 0.045);
            border-radius: 0;
            padding: 20px;
            min-height: 150px;
        }

        .step:last-child {
            border-right: none;
        }

        .step-num {
            color: var(--cream);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0.12em;
            margin-bottom: 8px;
        }

        .step-title {
            color: var(--text);
            font-size: 18px;
            font-weight: 720;
            margin-bottom: 4px;
        }

        .step-copy {
            color: var(--muted);
            font-size: 13px;
            line-height: 1.35;
        }

        .editorial-grid {
            display: grid;
            grid-template-columns: 1.2fr 0.8fr;
            gap: 0;
            border: 1px solid var(--line);
            margin-top: 18px;
        }

        .editorial-card {
            background: rgba(15, 15, 15, 0.90);
            padding: 28px;
            min-height: 240px;
            border-right: 1px solid var(--line);
            position: relative;
            overflow: hidden;
        }

        .editorial-card:last-child {
            border-right: 0;
        }

        .editorial-card::before {
            content: "";
            position: absolute;
            inset: auto -20% -50% 12%;
            height: 180px;
            background: radial-gradient(circle, rgba(227, 6, 19, 0.26), transparent 60%);
            pointer-events: none;
        }

        .editorial-kicker {
            color: var(--cream);
            font-size: 11px;
            letter-spacing: 0.14em;
            font-weight: 820;
            text-transform: uppercase;
            margin-bottom: 12px;
        }

        .editorial-title {
            color: var(--text);
            font-size: 28px;
            line-height: 1.08;
            font-weight: 820;
            max-width: 540px;
            margin-bottom: 10px;
        }

        .editorial-copy {
            color: var(--muted);
            font-size: 15px;
            line-height: 1.45;
            max-width: 560px;
        }

        .module-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0;
            border: 1px solid var(--line);
            margin-top: 20px;
        }

        .module-card {
            min-height: 220px;
            padding: 24px;
            background: rgba(10, 10, 10, 0.94);
            border-right: 1px solid var(--line);
            position: relative;
        }

        .module-card:last-child {
            border-right: 0;
        }

        .module-index {
            color: var(--red);
            font-size: 12px;
            letter-spacing: 0.14em;
            font-weight: 850;
            margin-bottom: 42px;
        }

        .module-title {
            color: var(--text);
            font-size: 24px;
            font-weight: 820;
            line-height: 1.08;
            margin-bottom: 8px;
        }

        .module-copy {
            color: var(--muted);
            font-size: 14px;
            line-height: 1.42;
        }

        div[data-testid="stMetric"] {
            background: rgba(15, 15, 15, 0.94);
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
            background: #111111;
            color: var(--text);
            font-weight: 720;
            min-height: 42px;
        }

        .stButton > button[kind="primary"] {
            color: #ffffff;
            border-color: rgba(255,255,255,0.20);
            background: linear-gradient(135deg, var(--red), #ff3340);
        }

        div[role="radiogroup"] label {
            border: 1px solid var(--line);
            border-radius: 0;
            background: rgba(255,255,255,0.04);
            padding: 9px 12px;
            margin-bottom: 8px;
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
            background: rgba(227, 6, 19, 0.32);
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
            .pipeline, .editorial-grid, .module-grid { grid-template-columns: 1fr; }
            .step, .editorial-card, .module-card { border-right: none; border-bottom: 1px solid var(--line); }
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
            <div class="site-nav">
                <div class="brand">OTC Algo</div>
                <div class="nav-items">
                    <span>Pipeline</span>
                    <span>Data</span>
                    <span>Backtest</span>
                    <span>Risk</span>
                </div>
            </div>
            <div class="hero-content">
                <div class="kicker">Internal dashboard</div>
                <div class="app-title">OTC scanner and backtest console.</div>
                <div class="app-subtitle">
                    IBKR data ingestion, universe discovery, signal scoring, liquidity-aware backtests, and risk monitoring. Live order routing is disabled.
                </div>
                <span class="badge green">Live trading disabled</span>
                <span class="badge pink">Paper orders disabled</span>
                <span class="badge blue">Entry ${settings['entry']['min_price']:.4f} to ${settings['entry']['max_price']:.4f}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def pipeline_strip() -> None:
    st.markdown(
        """
        <div class="pipeline">
            <div class="step"><div class="step-num">01</div><div class="step-title">Universe</div><div class="step-copy">Use IBKR scanner output to create or update the active symbol set.</div></div>
            <div class="step"><div class="step-num">02</div><div class="step-title">Market data</div><div class="step-copy">Fetch historical bars from TWS or IB Gateway in read-only mode.</div></div>
            <div class="step"><div class="step-num">03</div><div class="step-title">Signals</div><div class="step-copy">Apply entry, volume, liquidity, metadata, and risk filters.</div></div>
            <div class="step"><div class="step-num">04</div><div class="step-title">Backtest</div><div class="step-copy">Simulate next-day entries, partial fills, slippage, and risk exits.</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def editorial_modules() -> None:
    st.markdown(
        """
        <div class="editorial-grid">
            <div class="editorial-card">
                <div class="editorial-kicker">Pipeline</div>
                <div class="editorial-title">Run the data pipeline end to end.</div>
                <div class="editorial-copy">
                    Universe discovery, historical bar refresh, signal scan, and backtest run as one read-only sequence. Manual tools remain available for debugging.
                </div>
            </div>
            <div class="editorial-card">
                <div class="editorial-kicker">Execution boundary</div>
                <div class="editorial-title">No order routing.</div>
                <div class="editorial-copy">
                    IBKR is used for scanner and market-data requests only. Live and paper order flags remain disabled.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def module_grid() -> None:
    st.markdown(
        """
        <div class="module-grid">
            <div class="module-card">
                <div class="module-index">DISCOVERY</div>
                <div class="module-title">Universe management</div>
                <div class="module-copy">IBKR scanner output is saved as a local universe for repeatable scans and tests.</div>
            </div>
            <div class="module-card">
                <div class="module-index">RESEARCH</div>
                <div class="module-title">Signal filters</div>
                <div class="module-copy">Candidates are filtered by price range, volume breakout, dollar volume, metadata, spread, and guardrails.</div>
            </div>
            <div class="module-card">
                <div class="module-index">EXECUTION MODEL</div>
                <div class="module-title">Execution assumptions</div>
                <div class="module-copy">Backtests use limit-order assumptions, partial fills, slippage, and conservative exit liquidity.</div>
            </div>
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
    pages = ["Overview", "Pipeline", "Data", "Research", "Universe", "Ops"]
    if "requested_page" in st.session_state:
        st.session_state["page_nav"] = st.session_state.pop("requested_page")
    if "page_nav" not in st.session_state:
        st.session_state["page_nav"] = "Overview"

    st.markdown(
        """
        <div class="top-nav-shell">
            <div class="top-nav-title">OTC Algo</div>
            <div class="top-nav-meta">Internal research dashboard</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    page = st.radio(
        "Navigate",
        pages,
        key="page_nav",
        horizontal=True,
        label_visibility="collapsed",
    )

    with st.expander("Strategy settings", expanded=False):
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
        upsert_universe(universe_name, tickers, source=f"ibkr:{scan_code}:{location_code}", notes="Pipeline discovery", db_path=DB_PATH)

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
    page_header("Primary Workflow", "Run the data pipeline.", "Primary path: IBKR universe discovery, historical bar refresh, signal scan, and backtest.")
    pipeline_strip()
    if st.button("Run Pipeline", type="primary", use_container_width=True):
        st.session_state["requested_page"] = "Pipeline"
        st.rerun()
    editorial_modules()
    module_grid()


def render_autopilot(settings: dict) -> None:
    page_header("Pipeline", "Pipeline run.", "Run universe discovery, historical data refresh, signal scan, and backtest with one action.")
    st.warning("Read-only mode. No live or paper orders are sent.")

    config = ibkr_config("auto", default_client_id=17)
    html_panel("Pipeline parameters", "Configure scanner scope, data mode, and backtest input. The run saves a universe and refreshes price data before testing.")
    st.write("")
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
        submitted = st.form_submit_button("Run Pipeline", type="primary", use_container_width=True)

    if submitted:
        with st.spinner("Running data pipeline..."):
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
    page_header("Data", "Refresh market data and universes.", "IBKR is the primary data bridge. Alpha Vantage is available for basic OHLCV fallback.")
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
    page_header("Research", "Scan current candidates and run historical tests.", "Scanner shows current signals. Backtest uses historical bars and the configured execution assumptions.")
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
    page_header("Universe", "Saved universes.", "Review scanner output or import a controlled symbol list.")
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
    page_header("Ops", "Local setup and risk checks.", "Initialize local storage, load sample data, and run the monitor simulation.")
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
    if page == "Overview":
        render_command_center(settings)
    elif page == "Pipeline":
        render_autopilot(settings)
    elif page == "Data":
        render_data(settings)
    elif page == "Research":
        render_research(settings)
    elif page == "Universe":
        render_universe()
    elif page == "Ops":
        render_risk_admin(settings)


if __name__ == "__main__":
    main()
