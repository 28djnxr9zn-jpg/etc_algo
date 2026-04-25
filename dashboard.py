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


def inject_design() -> None:
    st.markdown(
        """
        <style>
        :root {
            --otc-bg: #080b10;
            --otc-panel: #10151d;
            --otc-card: #151b24;
            --otc-card-2: #0d1118;
            --otc-text: #f4f7fb;
            --otc-muted: #9aa6b2;
            --otc-line: rgba(255, 255, 255, 0.10);
            --otc-blue: #2dd4ff;
            --otc-green: #39ff88;
            --otc-red: #ff3b6b;
            --otc-amber: #ffcc33;
        }

        .stApp {
            background: var(--otc-bg);
            color: var(--otc-text);
        }

        header[data-testid="stHeader"] {
            background: rgba(8, 11, 16, 0.78);
            backdrop-filter: blur(18px);
        }

        section[data-testid="stSidebar"] {
            background: #0b0f16;
            border-right: 1px solid var(--otc-line);
        }

        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: var(--otc-text);
            font-weight: 650;
            letter-spacing: 0;
        }

        .block-container {
            padding-top: 1.65rem;
            padding-bottom: 4rem;
            max-width: 1220px;
        }

        h1, h2, h3 {
            color: var(--otc-text);
            letter-spacing: 0;
        }

        h1 {
            font-size: 56px !important;
            line-height: 1.04 !important;
            font-weight: 700 !important;
        }

        h2 {
            font-size: 32px !important;
            line-height: 1.15 !important;
            font-weight: 680 !important;
        }

        h3 {
            font-size: 20px !important;
            font-weight: 650 !important;
        }

        p, label, .stCaption, [data-testid="stMarkdownContainer"] {
            color: var(--otc-muted);
            letter-spacing: 0;
        }

        .otc-hero {
            position: relative;
            overflow: hidden;
            padding: 42px 34px 34px;
            text-align: left;
            background:
                linear-gradient(135deg, rgba(45, 212, 255, 0.18), rgba(57, 255, 136, 0.08) 42%, rgba(255, 59, 107, 0.10)),
                #0d1118;
            border: 1px solid var(--otc-line);
            border-radius: 24px;
            box-shadow: 0 24px 80px rgba(0, 0, 0, 0.34);
        }

        .otc-eyebrow {
            color: var(--otc-blue);
            font-size: 13px;
            line-height: 1.35;
            font-weight: 760;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            margin-bottom: 10px;
        }

        .otc-title {
            color: var(--otc-text);
            font-size: 56px;
            line-height: 1.02;
            font-weight: 720;
            letter-spacing: 0;
            margin: 0 0 12px;
            max-width: 820px;
        }

        .otc-subtitle {
            color: var(--otc-muted);
            font-size: 19px;
            line-height: 1.32;
            font-weight: 400;
            max-width: 760px;
            margin: 0;
        }

        .otc-section {
            margin-top: 28px;
            margin-bottom: 10px;
        }

        .otc-section h2 {
            margin-bottom: 4px;
        }

        .otc-section p {
            font-size: 17px;
            line-height: 1.45;
            margin-top: 0;
        }

        .otc-card {
            background: var(--otc-card);
            border: 1px solid var(--otc-line);
            border-radius: 14px;
            padding: 22px 24px;
            min-height: 124px;
            box-shadow: 0 14px 40px rgba(0, 0, 0, 0.22);
        }

        .otc-card-title {
            color: var(--otc-text);
            font-size: 19px;
            line-height: 1.25;
            font-weight: 680;
            margin-bottom: 8px;
        }

        .otc-card-body {
            color: var(--otc-muted);
            font-size: 15px;
            line-height: 1.4;
        }

        .otc-status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 11px;
            border-radius: 999px;
            background: #eef6ff;
            color: #0057b8;
            font-size: 13px;
            font-weight: 650;
            margin: 4px 6px 4px 0;
        }

        .otc-status.safe {
            background: rgba(57, 255, 136, 0.12);
            color: var(--otc-green);
        }

        .otc-status.off {
            background: rgba(255, 255, 255, 0.09);
            color: var(--otc-muted);
        }

        .otc-status {
            background: rgba(45, 212, 255, 0.12);
            color: var(--otc-blue);
        }

        div[data-testid="stMetric"] {
            background: var(--otc-card);
            border: 1px solid var(--otc-line);
            border-radius: 14px;
            padding: 18px 20px;
            box-shadow: 0 14px 40px rgba(0, 0, 0, 0.18);
        }

        div[data-testid="stMetricLabel"] p {
            color: var(--otc-muted);
            font-size: 13px;
            font-weight: 600;
        }

        div[data-testid="stMetricValue"] {
            color: var(--otc-text);
            font-weight: 680;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--otc-line);
            border-radius: 14px;
            padding: 6px;
            width: fit-content;
            margin-bottom: 22px;
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 10px;
            padding: 8px 16px;
            color: var(--otc-muted);
            font-weight: 600;
        }

        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(45, 212, 255, 0.28), rgba(57, 255, 136, 0.18));
            color: var(--otc-text);
        }

        div[role="radiogroup"] label {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 12px;
            padding: 8px 10px;
            margin-bottom: 6px;
        }

        .stButton > button {
            border-radius: 12px;
            border: 1px solid var(--otc-line);
            padding: 0.62rem 1.1rem;
            font-weight: 650;
            background: #111823;
            color: var(--otc-text);
        }

        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, var(--otc-blue), var(--otc-green));
            color: #061014;
            border-color: rgba(255, 255, 255, 0.18);
        }

        .otc-page-head {
            margin-bottom: 22px;
            padding-bottom: 14px;
            border-bottom: 1px solid var(--otc-line);
        }

        .otc-page-kicker {
            color: var(--otc-blue);
            font-size: 12px;
            font-weight: 760;
            text-transform: uppercase;
            letter-spacing: 0.14em;
            margin-bottom: 8px;
        }

        .otc-page-title {
            color: var(--otc-text);
            font-size: 36px;
            font-weight: 720;
            line-height: 1.08;
        }

        .otc-page-body {
            color: var(--otc-muted);
            font-size: 16px;
            line-height: 1.45;
            max-width: 820px;
            margin-top: 8px;
        }

        .stDataFrame, div[data-testid="stTable"] {
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid var(--otc-line);
        }

        div[data-testid="stAlert"] {
            border-radius: 14px;
            border: 1px solid var(--otc-line);
        }

        input, textarea, div[data-baseweb="select"] > div {
            border-radius: 10px !important;
        }

        hr {
            border-color: var(--otc-line);
        }

        @media (max-width: 760px) {
            .otc-title {
                font-size: 42px;
            }
            .otc-subtitle {
                font-size: 18px;
            }
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(settings: dict) -> None:
    st.markdown(
        f"""
        <section class="otc-hero">
            <div class="otc-eyebrow">OTC Algo</div>
            <div class="otc-title">Disciplined scanning for speculative markets.</div>
            <div class="otc-subtitle">
                Discover a universe, refresh IBKR data, scan candidates, and run liquidity-aware backtests.
                Live trading stays disabled.
            </div>
            <div style="margin-top:22px;">
                <span class="otc-status safe">Live trading disabled</span>
                <span class="otc-status off">Paper orders disabled</span>
                <span class="otc-status">Entry range ${settings['entry']['min_price']:.4f} to ${settings['entry']['max_price']:.4f}</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="otc-section">
            <h2>{title}</h2>
            <p>{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(kicker: str, title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="otc-page-head">
            <div class="otc-page-kicker">{kicker}</div>
            <div class="otc-page-title">{title}</div>
            <div class="otc-page-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_card(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="otc-card">
            <div class="otc-card-title">{title}</div>
            <div class="otc-card-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
        upsert_universe(
            universe_name,
            tickers,
            source=f"ibkr:{scan_code}:{location_code}",
            notes="Autonomous pipeline discovery",
            db_path=DB_PATH,
        )

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
    st.sidebar.title("OTC Algo")
    st.sidebar.caption("Autonomous research cockpit")

    st.sidebar.divider()
    st.sidebar.subheader("Strategy")
    st.sidebar.caption("Entry")
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

    st.sidebar.caption("Watchlist")
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

    st.sidebar.caption("Tradable")
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

    st.sidebar.caption("Sizing")
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

    st.sidebar.caption("Risk exits")
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

    st.sidebar.caption("Safety")
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
    render_section("Database", "Initialize local storage or load the included demo dataset.")
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


def render_overview(settings: dict) -> None:
    render_page_header(
        "Command Center",
        "Research pipeline at a glance.",
        "Start with Autopilot for an automated run, or step into Data Hub and Research when you need manual control.",
    )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Database", "Ready" if database_has_data() else "Empty")
    with col2:
        st.metric("Universes", len(saved_universe_names()))
    with col3:
        st.metric("Live trading", "Off")
    with col4:
        st.metric("Paper orders", "Off")

    st.write("")
    c1, c2 = st.columns([1.2, 0.8])
    with c1:
        render_card(
            "Autopilot is the primary workflow",
            "It discovers a universe through IBKR, saves it, refreshes bars, scans the database, and runs a backtest without placing orders.",
        )
    with c2:
        render_card(
            "System boundary",
            "Live trading and paper order placement are hard-disabled. This is research, simulation, and monitoring only.",
        )

    st.write("")
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        render_card("Discover", "IBKR scanner finds candidates.")
    with s2:
        render_card("Refresh", "TWS/Gateway provides bars.")
    with s3:
        render_card("Rank", "Scanner scores tradability.")
    with s4:
        render_card("Simulate", "Backtest models fills and exits.")


def render_autopilot(settings: dict) -> None:
    render_page_header(
        "Autopilot",
        "Run the full research loop.",
        "Discover a universe from IBKR, fetch historical bars, scan, and backtest in one read-only operation.",
    )
    st.warning("Autopilot is research-only. Live trading and paper order placement remain disabled.")

    col1, col2, col3 = st.columns(3)
    host = col1.text_input("IBKR host", value="127.0.0.1", key="auto_host")
    port = col2.number_input("IBKR port", min_value=1, max_value=65535, value=7497, key="auto_port")
    client_id = col3.number_input("Client ID", min_value=1, max_value=9999, value=17, key="auto_client")
    config = IBKRConnectionConfig(host=host, port=int(port), client_id=int(client_id), readonly=True)

    col4, col5, col6 = st.columns(3)
    scan_code = col4.selectbox(
        "Discovery scanner",
        ["HOT_BY_VOLUME", "TOP_PERC_GAIN", "MOST_ACTIVE", "TOP_TRADE_COUNT", "HOT_BY_PRICE"],
        index=0,
        key="auto_scan",
    )
    location_code = col5.text_input("Scanner location", value="STK.US", key="auto_location")
    max_results = col6.number_input("Max discovered symbols", min_value=1, max_value=200, value=50, step=10, key="auto_max_results")

    col7, col8, col9 = st.columns(3)
    min_price = col7.number_input("Discovery min price", min_value=0.0, value=float(settings["entry"]["min_price"]), step=0.0001, format="%.4f", key="auto_min_price")
    max_price = col8.number_input("Discovery max price", min_value=0.0, value=float(settings["entry"]["max_price"]), step=0.01, format="%.4f", key="auto_max_price")
    min_volume = col9.number_input("Discovery min volume", min_value=0, value=0, step=10000, key="auto_min_volume")

    col10, col11, col12 = st.columns(3)
    universe_name = col10.text_input("Universe name", value="autopilot_ibkr", key="auto_universe")
    duration = col11.selectbox("History", ["30 D", "60 D", "6 M", "1 Y"], index=1, key="auto_duration")
    market_data_type = col12.selectbox("Data mode", ["Live", "Delayed", "Frozen", "Delayed frozen"], index=1, key="auto_data_mode")

    col13, col14 = st.columns(2)
    what_to_show = col13.selectbox("Bar type", ["TRADES", "MIDPOINT", "BID", "ASK"], index=0, key="auto_bar_type")
    use_rth = col14.checkbox("Regular hours only", value=False, key="auto_rth")

    if st.button("Run Autopilot", type="primary", use_container_width=True):
        with st.spinner("Running autonomous research pipeline..."):
            result = run_autonomous_pipeline(
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

        discovered = result["discovered"]
        prices = result["prices"]
        backtest_result = result["backtest"]

        scol1, scol2, scol3 = st.columns(3)
        scol1.metric("Discovered", 0 if discovered.empty else discovered["ticker"].nunique())
        scol2.metric("Price rows", len(prices))
        scol3.metric("Trades", 0 if not backtest_result else backtest_result["metrics"]["number_of_trades"])

        if result["discovery_errors"]:
            st.warning("Discovery messages:\n\n" + "\n".join(result["discovery_errors"]))
        if result["fetch_errors"]:
            st.warning("Fetch messages:\n\n" + "\n".join(result["fetch_errors"]))

        tabs = st.tabs(["Discovered", "Prices", "Backtest"])
        with tabs[0]:
            if not discovered.empty:
                st.dataframe(discovered, use_container_width=True, hide_index=True)
            else:
                st.info("No symbols discovered.")
        with tabs[1]:
            if not prices.empty:
                st.dataframe(prices.sort_values(["ticker", "date"], ascending=[True, False]).head(100), use_container_width=True, hide_index=True)
            else:
                st.info("No prices loaded.")
        with tabs[2]:
            if backtest_result:
                metrics = backtest_result["metrics"]
                st.dataframe(pd.DataFrame([metrics]), use_container_width=True, hide_index=True)
                equity = pd.DataFrame(backtest_result["equity_curve"])
                if not equity.empty:
                    st.line_chart(equity.set_index("date")["portfolio_value"])
                trades = pd.DataFrame(backtest_result["trades"])
                if not trades.empty:
                    st.dataframe(trades, use_container_width=True, hide_index=True)
            else:
                st.info("Backtest did not run because no price data was loaded.")


def render_universe() -> None:
    render_page_header("Universe", "Manage saved symbol sets.", "Review discovered universes or import your own CSV when you want a controlled watch universe.")

    names = saved_universe_names()
    if names:
        selected = st.selectbox("Saved universes", names)
        tickers = get_universe_tickers(selected, DB_PATH)
        st.metric("Tickers", len(tickers))
        st.dataframe(pd.DataFrame({"ticker": tickers}), use_container_width=True, hide_index=True)
    else:
        st.info("No universes saved yet. Create one below or load sample data.")

    st.divider()
    st.markdown("### Create or Replace")
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
    render_page_header(
        "Fallback Data",
        "Alpha Vantage price import.",
        "Fetch real OHLCV price history when IBKR is not available. This does not include OTC metadata, catalysts, or Level 2 depth.",
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
    render_page_header("IBKR", "Primary market data bridge.", "Connect through TWS or IB Gateway in read-only mode. This dashboard does not place orders.")

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
        st.markdown("### Discover Universe")
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
        st.markdown("### Historical Bars")
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
        st.markdown("### Level 2 Snapshot")
        st.caption("Request an IBKR market-depth snapshot with `reqMktDepth`.")
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
    render_page_header("Scanner", "Inspect current candidates.", "Rank the currently loaded database symbols using the strategy filters and scoring model.")
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
    render_page_header("Backtest", "Test the strategy honestly.", "Signals are generated after the close. Entries are simulated on the next available trading day.")
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
    render_page_header("Monitor", "Risk watch simulation.", "Simulate a 15-minute risk check. The monitor only recommends actions.")
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


def render_data_hub(settings: dict) -> None:
    provider = st.radio("Data source", ["IBKR", "Alpha Vantage"], horizontal=True)
    st.write("")
    if provider == "IBKR":
        render_ibkr_data(settings)
    else:
        render_live_data(settings)


def render_research(settings: dict) -> None:
    mode = st.radio("Research view", ["Scanner", "Backtest"], horizontal=True)
    st.write("")
    if mode == "Scanner":
        render_scanner(settings)
    else:
        render_backtest(settings)


def render_admin() -> None:
    render_page_header("Admin", "Local project controls.", "Initialize the database, load demo data, and confirm local state.")
    render_database_controls()


def main() -> None:
    inject_design()
    settings = settings_from_sidebar()
    st.sidebar.divider()
    page = st.sidebar.radio(
        "Navigate",
        ["Command Center", "Autopilot", "Data Hub", "Research", "Universe", "Risk Monitor", "Admin"],
        index=0,
    )

    if page == "Command Center":
        render_hero(settings)
        render_overview(settings)
    elif page == "Autopilot":
        render_autopilot(settings)
    elif page == "Data Hub":
        render_data_hub(settings)
    elif page == "Research":
        render_research(settings)
    elif page == "Universe":
        render_universe()
    elif page == "Risk Monitor":
        render_monitor(settings)
    elif page == "Admin":
        render_admin()


if __name__ == "__main__":
    main()
