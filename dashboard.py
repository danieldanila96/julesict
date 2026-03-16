import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import glob
import sqlite3
import datetime
from dotenv import set_key, load_dotenv

from backtester import load_data, run_backtest
from ict_engine import detect_fvg, get_daily_bias, calculate_po3_levels, detect_smt_divergence
import config_manager as cm

# Force dark theme via page config and CSS
st.set_page_config(page_title="LiquidX Terminal", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    /* Add any custom CSS styling here if needed */
    .metric-card {
        background-color: #1e1e1e;
        padding: 15px;
        border-radius: 5px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.sidebar.title("LiquidX Terminal")

# --- PROFILE SELECTION ---
active_profile = cm.get_active_profile_name()
all_profiles = cm.list_profiles()

st.sidebar.subheader("Configuration Profile")
selected_profile = st.sidebar.selectbox("Active Profile", all_profiles, index=all_profiles.index(active_profile))

if selected_profile != active_profile:
    cm.set_active_profile(selected_profile)
    st.rerun()

config = cm.load_profile(selected_profile)

# --- NAVIGATION ---
page = st.sidebar.radio("Navigation", [
    "Overview",
    "Strategy Settings",
    "Risk Settings",
    "Broker / Account",
    "Backtest Runner",
    "Live / Paper Control",
    "Trade History",
    "Logs / Debug",
    "Data Management"
])

# --- HELPER FUNCS ---
def update_config(section, key, val):
    if section not in config:
        config[section] = {}
    config[section][key] = val
    cm.save_profile(selected_profile, config)

def get_config(section, key, default):
    return config.get(section, {}).get(key, default)

# --- PAGES ---

if page == "Overview":
    st.title("LiquidX - Overview")
    st.markdown(f"**Current Profile:** `{selected_profile}` | **Mode:** `{get_config('General', 'mode', 'Backtest')}`")

    col1, col2, col3 = st.columns(3)
    col1.metric("Symbol", get_config('Market', 'symbol', 'ES').upper())
    col2.metric("Timeframe", get_config('Market', 'timeframe', '5m').upper())
    col3.metric("Risk Per Trade", f"${get_config('Risk', 'risk_per_trade_usd', 1000.0):.2f}")

    st.divider()
    st.subheader("Profile Management")
    new_profile_name = st.text_input("New Profile Name")
    if st.button("Save As New Profile"):
        if new_profile_name:
            cm.save_profile(new_profile_name, config)
            cm.set_active_profile(new_profile_name)
            st.success(f"Created and activated profile: {new_profile_name}")
            st.rerun()

    if st.button("Reset to Defaults"):
        if selected_profile == cm.DEFAULT_PROFILE:
            st.warning("Cannot delete default profile, but it has been reset.")
            cm.save_profile(cm.DEFAULT_PROFILE, cm.DEFAULT_CONFIG)
        else:
            cm.delete_profile(selected_profile)
            st.success("Deleted profile.")
        st.rerun()

elif page == "Strategy Settings":
    st.title("Strategy Settings")
    st.markdown("Configure the Inner Circle Trader (ICT) logic engines.")

    with st.form("strategy_form"):
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Core Toggles")
            enable_fvg = st.checkbox("Enable FVG Logic", value=get_config('Strategy', 'enable_fvg', True))
            enable_dol = st.checkbox("Enable DOL (Draw on Liquidity)", value=get_config('Strategy', 'enable_dol', True))
            enable_smt = st.checkbox("Enable SMT Divergence", value=get_config('Strategy', 'enable_smt', True))
            enable_po3 = st.checkbox("Enable PO3 (Midnight Open Manipulation)", value=get_config('Strategy', 'enable_po3', True))

            st.subheader("Market & Timeframes")
            symbol = st.text_input("Symbol", value=get_config('Market', 'symbol', 'es'))
            ltf = st.text_input("Execution Timeframe", value=get_config('Market', 'timeframe', '5m'))
            htf = st.text_input("Higher Timeframe (Bias)", value=get_config('Market', 'htf', '1h'))

        with col2:
            st.subheader("Thresholds")
            fvg_buffer = st.number_input("FVG Stop Loss Buffer (%)", value=get_config('Strategy', 'fvg_buffer_pct', 0.001), format="%.5f")
            min_rr = st.number_input("Minimum Risk/Reward (RR)", value=get_config('Strategy', 'min_rr', 1.2), step=0.1)

            st.subheader("Session Killzones (Minutes from 00:00)")
            lon_start = st.number_input("London Start", value=get_config('Market', 'london_start', 60))
            lon_end = st.number_input("London End", value=get_config('Market', 'london_end', 360))
            ny_start = st.number_input("NY Start", value=get_config('Market', 'ny_start', 510))
            ny_end = st.number_input("NY End", value=get_config('Market', 'ny_end', 960))

        submit = st.form_submit_button("Save Strategy Settings")
        if submit:
            update_config('Strategy', 'enable_fvg', enable_fvg)
            update_config('Strategy', 'enable_dol', enable_dol)
            update_config('Strategy', 'enable_smt', enable_smt)
            update_config('Strategy', 'enable_po3', enable_po3)
            update_config('Strategy', 'fvg_buffer_pct', fvg_buffer)
            update_config('Strategy', 'min_rr', min_rr)

            update_config('Market', 'symbol', symbol.lower())
            update_config('Market', 'timeframe', ltf.lower())
            update_config('Market', 'htf', htf.lower())
            update_config('Market', 'london_start', int(lon_start))
            update_config('Market', 'london_end', int(lon_end))
            update_config('Market', 'ny_start', int(ny_start))
            update_config('Market', 'ny_end', int(ny_end))

            st.success("Strategy config saved!")

elif page == "Risk Settings":
    st.title("Risk Management")
    with st.form("risk_form"):
        risk_usd = st.number_input("Risk Per Trade (USD)", value=get_config('Risk', 'risk_per_trade_usd', 1000.0), step=100.0)
        pt_val = st.number_input("Point Value (Multiplier)", value=get_config('Risk', 'point_value', 50.0), step=1.0)

        submit = st.form_submit_button("Save Risk Settings")
        if submit:
            update_config('Risk', 'risk_per_trade_usd', risk_usd)
            update_config('Risk', 'point_value', pt_val)
            st.success("Risk config saved!")

elif page == "Broker / Account":
    st.title("Broker Integration")
    st.markdown("Configure Topstep API settings.")

    # Initialize the QuantX Connector to fetch actual contracts if authenticated
    try:
        from broker_connector import QuantXConnector
        connector = QuantXConnector()
        auth_success = connector.authenticate()
        auth_error = None
    except Exception as e:
        connector = None
        auth_success = False
        auth_error = str(e)

    st.subheader("Topstep Instruments")
    if auth_error:
        st.error(f"Error loading broker integration modules: {auth_error}")
    if auth_success and connector:
        symbol_query = st.text_input("Query Symbol Contracts (e.g. NQ, ES)", value=get_config('Market', 'symbol', 'ES').upper())
        if symbol_query:
            contracts = connector.search_contracts(symbol_query)
            if contracts and len(contracts) > 0 and contracts[0].get('id') != 'MOCK.CON':
                # Map contracts into a selectbox
                contract_options = {f"{c['name']} ({c['description']})": c['id'] for c in contracts}
                selected_contract_name = st.selectbox("Select Active Contract for Trading", list(contract_options.keys()))

                if st.button("Set as Primary Instrument"):
                    update_config('Market', 'symbol', symbol_query.lower())

                    env_path = "QuantX/backend/.env"
                    set_key(env_path, "CONTRACT_ID", contract_options[selected_contract_name])

                    st.success(f"Instrument locked to: {contract_options[selected_contract_name]}")
            else:
                st.warning(f"No contracts found for {symbol_query}")
    else:
        st.warning("Not authenticated with Topstep API. Please configure credentials below to pull live instruments.")

    st.divider()

    # Load env for display/editing
    load_dotenv("QuantX/backend/.env")

    with st.form("broker_form"):
        acc_id = st.text_input("Account ID", value=os.getenv("ACCOUNT_ID", ""))
        api_key = st.text_input("API Key", value=os.getenv("API_KEY", ""), type="password")
        session_token = st.text_input("Session Token", value=os.getenv("SESSION_TOKEN", ""), type="password")
        username = st.text_input("Username (Email)", value=os.getenv("USERNAME", ""))

        mode = st.selectbox("Bot Operation Mode", ["Backtest", "Paper", "Live"], index=["Backtest", "Paper", "Live"].index(get_config("General", "mode", "Backtest")))

        submit = st.form_submit_button("Save Broker Config")
        if submit:
            # We save the mode to config
            update_config("General", "mode", mode)

            # We save the credentials to .env for safety
            env_path = "QuantX/backend/.env"
            set_key(env_path, "ACCOUNT_ID", acc_id)
            set_key(env_path, "API_KEY", api_key)
            set_key(env_path, "TOPSTEP_API_KEY", api_key)
            set_key(env_path, "SESSION_TOKEN", session_token)
            set_key(env_path, "USERNAME", username)

            st.success("Broker settings and mode saved!")

    if st.button("Test Connection"):
        with st.spinner("Connecting to QuantX..."):
            try:
                from broker_connector import QuantXConnector
                connector = QuantXConnector()
                if connector.authenticate():
                    st.success("Successfully authenticated with API.")
                else:
                    st.error("Failed to authenticate.")
            except Exception as e:
                st.error(f"Error connecting: {e}")

elif page == "Backtest Runner":
    st.title("Backtest Runner")
    st.markdown(f"Running strategy against historical data using active profile: `{selected_profile}`")

    with st.form("backtest_form"):
        st.subheader("Backtest Parameters")
        col1, col2, col3 = st.columns(3)

        # Pull parameters so users can override standard strategy settings for this run
        sym = col1.text_input("Symbol", value=get_config("Market", "symbol", "es"))
        ltf = col2.text_input("Execution Timeframe", value=get_config("Market", "timeframe", "5m"))
        htf = col3.text_input("Higher Timeframe", value=get_config("Market", "htf", "1h"))

        start_d = col1.date_input("Start Date", value=datetime.date(2025, 1, 1))
        end_d = col2.date_input("End Date", value=datetime.date.today())

        init_cap = col1.number_input("Initial Capital", value=get_config("Backtest", "initial_capital", 100000.0), step=1000.0)
        comm = col2.number_input("Commission (Per Side)", value=get_config("Backtest", "commission", 2.0), step=0.1)
        slip = col3.number_input("Slippage (Points)", value=get_config("Backtest", "slippage", 0.25), step=0.25)

        submit = st.form_submit_button("Run Backtest")

        if submit:
            update_config("Market", "symbol", sym.lower())
            update_config("Market", "timeframe", ltf.lower())
            update_config("Market", "htf", htf.lower())
            update_config("Backtest", "start_date", start_d.strftime("%Y-%m-%d"))
            update_config("Backtest", "end_date", end_d.strftime("%Y-%m-%d"))
            update_config("Backtest", "initial_capital", init_cap)
            update_config("Backtest", "commission", comm)
            update_config("Backtest", "slippage", slip)

            with st.spinner("Simulating historical execution..."):
                results = run_backtest(selected_profile)

                if "error" in results:
                    st.error(results["error"])
                else:
                    st.session_state['bt_results'] = results
                    st.success("Backtest complete!")

    if 'bt_results' in st.session_state:
        res = st.session_state['bt_results']
        stats = res['stats']
        df_trades = res['trades']

        st.subheader("Performance Analytics")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Final Capital", f"${stats['final_capital']:,.2f}", f"{stats['return_pct']:.2f}%")
        col2.metric("Total PnL", f"${stats['total_pnl']:,.2f}")
        col3.metric("Win Rate", f"{stats['win_rate']:.2f}%", f"{stats['winning_trades']}W / {stats['losing_trades']}L")
        col4.metric("Profit Factor", f"{stats['profit_factor']:.2f}")

        st.subheader("Equity Curve")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_trades['Date'], y=df_trades['Cumulative Equity'], mode='lines', name='Equity', line=dict(color='#00ff00')))
        fig.update_layout(template='plotly_dark', xaxis_title="Date", yaxis_title="Capital ($)")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Trade Log")
        st.dataframe(df_trades, use_container_width=True)

elif page == "Live / Paper Control":
    st.title("Execution Dashboard")
    mode = get_config("General", "mode", "Backtest")
    bot_status = get_config("General", "bot_status", "Stopped")

    st.markdown(f"**Current Mode:** `{mode}` | **Bot Status:** `{bot_status}`")

    if mode == "Backtest":
        st.warning("Bot is currently in Backtest mode. Go to Broker / Account settings to switch to Paper or Live.")

    st.subheader("Daemon Controls")
    st.info("Start the execution loop externally via `python engine.py` or a process manager. Use the controls below to dictate the daemon's runtime state.")

    col1, col2, col3 = st.columns(3)
    if col1.button("▶️ Start Bot", disabled=(bot_status == "Running")):
        update_config("General", "bot_status", "Running")
        st.success("Bot signal sent: RUNNING")
        st.rerun()
    if col2.button("⏸️ Pause Entries", disabled=(bot_status == "Paused")):
        update_config("General", "bot_status", "Paused")
        st.warning("Bot signal sent: PAUSED (Will manage existing trades, but take no new ones)")
        st.rerun()
    if col3.button("⏹️ Stop Bot", disabled=(bot_status == "Stopped")):
        update_config("General", "bot_status", "Stopped")
        st.error("Bot signal sent: STOPPED")
        st.rerun()

    st.divider()

    st.subheader("Live Market Context")
    try:
        data = load_data('tradingdata')
        sym = get_config("Market", "symbol", "es").lower()
        ltf = get_config("Market", "timeframe", "5m")
        if sym in data and ltf in data[sym]:
            df = data[sym][ltf]
            last_price = df['Close'].iloc[-1]
            last_time = df['Time'].iloc[-1]
            st.metric(f"{sym.upper()} Current Price", f"{last_price:.2f}", f"As of {last_time}")
        else:
            st.warning("Market data unavailable.")
    except Exception as e:
        st.error("Error loading market context.")

    st.subheader("Open Positions (Local State)")
    try:
        conn = sqlite3.connect('liquidx.db')
        df_open = pd.read_sql_query("SELECT * FROM trades WHERE status = 'OPEN'", conn)
        conn.close()

        if not df_open.empty:
            st.dataframe(df_open, use_container_width=True)
        else:
            st.info("No active trades.")
    except Exception as e:
        st.warning("Database not initialized or empty.")

elif page == "Trade History":
    st.title("Historical Live Trades")
    try:
        conn = sqlite3.connect('liquidx.db')
        df_all = pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC", conn)
        conn.close()

        if df_all.empty:
            st.info("No trades executed yet.")
        else:
            col1, col2, col3 = st.columns(3)
            sym_filter = col1.selectbox("Filter Symbol", ["All"] + list(df_all['symbol'].unique()))
            dir_filter = col2.selectbox("Filter Direction", ["All", "Long", "Short"])
            status_filter = col3.selectbox("Filter Status", ["All", "OPEN", "CLOSED"])

            if sym_filter != "All":
                df_all = df_all[df_all['symbol'] == sym_filter]
            if dir_filter != "All":
                df_all = df_all[df_all['direction'] == dir_filter]
            if status_filter != "All":
                df_all = df_all[df_all['status'] == status_filter]

            st.dataframe(df_all, use_container_width=True)
    except Exception as e:
        st.warning("Database not found.")

elif page == "Logs / Debug":
    st.title("System Logs")
    if os.path.exists('logs/liquidx.log'):
        with open('logs/liquidx.log', 'r') as f:
            logs = f.readlines()

        st.code("".join(logs[-100:]), language="text") # Show last 100 lines
    else:
        st.info("No log file found at logs/liquidx.log")

elif page == "Data Management":
    st.title("Data Management")
    st.markdown("Current market data loaded in `/tradingdata`")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Available Datasets")
        files = glob.glob("tradingdata/*.csv")
        if files:
            for f in files:
                size = os.path.getsize(f) / 1024 # KB
                st.text(f"📄 {os.path.basename(f)} ({size:.1f} KB)")
        else:
            st.info("No data files found.")

    with col2:
        st.subheader("Upload New Data")
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded_file is not None:
            if not os.path.exists('tradingdata'):
                os.makedirs('tradingdata')
            with open(os.path.join('tradingdata', uploaded_file.name), 'wb') as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"Saved {uploaded_file.name} to tradingdata!")
            st.rerun()

        if st.button("Reload Data Cache"):
            # Streamlit clears cache decorators with clear()
            st.cache_data.clear()
            st.success("Cache cleared. Data will be reloaded on next query.")
