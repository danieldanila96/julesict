import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import numpy as np
from backtester import load_data
from ict_engine import detect_fvg, get_daily_bias, calculate_po3_levels

# Configure Streamlit page
st.set_page_config(
    page_title="LiquidX Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for dark theme adjustments (Streamlit's default dark mode handles most of this, but we can tweak)
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        height: 60px;
        font-size: 20px;
        font-weight: bold;
        background-color: #ff4b4b;
        color: white;
        border-radius: 5px;
        border: none;
    }
    .stButton>button:hover {
        background-color: #ff3333;
        color: white;
    }
    .metric-card {
        background-color: #1e1e1e;
        padding: 15px;
        border-radius: 5px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# Application Title
st.title("LiquidX Trading Terminal")
st.markdown("Automated ICT Setup Execution - S&P500")

# --- DATA LOADING & PROCESSING ---
@st.cache_data(ttl=300) # Cache for 5 minutes
def fetch_and_process_data():
    data = load_data('tradingdata')
    if not data or '5m' not in data or '1h' not in data or 'daily' not in data:
        return None, "Error: Missing required timeframes in tradingdata folder."

    df_daily = data['daily']
    df_1h = data['1h']
    df_5m = data['5m']

    # Get the latest state
    # 1. 1H FVGs for higher timeframe targets
    h1_fvgs = detect_fvg(df_1h)

    # 2. Daily Bias
    # Pass the daily df minus the current unclosed day to get previous day high/low correctly
    daily_history = df_daily.iloc[:-1].copy() if len(df_daily) > 1 else df_daily.copy()
    current_price = df_5m['Close'].iloc[-1]
    bias_info = get_daily_bias(daily_history, h1_fvgs, current_price)

    # 3. PO3 Levels based on current day 5m data
    current_date = df_5m['Time'].dt.date.iloc[-1]
    day_5m = df_5m[df_5m['Time'].dt.date == current_date].copy()
    po3_info = calculate_po3_levels(day_5m, bias=bias_info['bias'])

    # 4. 5M FVGs for visual chart
    m5_fvgs = detect_fvg(df_5m.tail(100)) # Only need recent ones for chart

    return {
        'df_5m': df_5m,
        'bias_info': bias_info,
        'po3_info': po3_info,
        'm5_fvgs': m5_fvgs,
        'current_price': current_price
    }, None

# Load data
with st.spinner("Loading market data and calculating technicals..."):
    app_state, error = fetch_and_process_data()

if error:
    st.error(error)
    st.stop()

df_5m = app_state['df_5m']
bias_info = app_state['bias_info']
po3_info = app_state['po3_info']
m5_fvgs = app_state['m5_fvgs']
current_price = app_state['current_price']

# --- SIDEBAR: THE DAILY CHECKLIST ---
with st.sidebar:
    st.header("The Daily Checklist")

    # Check 1: Daily Bias Set
    bias = bias_info['bias']
    bias_color = "green" if bias == "Bullish" else "red" if bias == "Bearish" else "gray"
    bias_checked = bias != "Neutral"
    st.checkbox("Daily Bias Set", value=bias_checked, disabled=True)
    if bias_checked:
        st.markdown(f"**Bias:** <span style='color:{bias_color}'>{bias}</span>", unsafe_allow_html=True)
        if bias_info['dol']:
            st.markdown(f"**DOL:** {bias_info['dol'][0]} @ {bias_info['dol'][1]:.2f}")

    # Check 2: High Impact News
    st.checkbox("High Impact News Cleared", value=True) # Mocked to True for now

    # Check 3: Midnight Open Manipulation
    po3_phase = po3_info.get('po3_phase', 'Unknown')
    manip_checked = "Manipulation" in po3_phase or "Distribution" in po3_phase
    st.checkbox("Midnight Open Manipulation Detected", value=manip_checked, disabled=True)
    if manip_checked:
        st.markdown(f"**Current Phase:** {po3_phase}")
        st.markdown(f"**Midnight Open:** {po3_info.get('midnight_open', 0):.2f}")

    st.divider()

    st.header("Risk Settings")
    risk_per_trade = st.number_input("Risk per Trade ($)", min_value=100, max_value=5000, value=1000, step=100)

    st.divider()

    # --- TRADE TERMINAL ---
    st.header("Trade Terminal")
    st.write("Ready to execute based on active 5M FVG and Bias.")

    # Find nearest valid entry FVG
    valid_entry = None
    unfilled_m5_fvgs = [f for f in m5_fvgs if not f['filled']]
    if bias == 'Bullish':
        bullish_fvgs = [f for f in unfilled_m5_fvgs if f['type'] == 1 and f['bottom'] < current_price]
        if bullish_fvgs:
            valid_entry = max(bullish_fvgs, key=lambda x: x['top'])
            trade_dir = "Long"
            sl = valid_entry['bottom'] - 1
    elif bias == 'Bearish':
        bearish_fvgs = [f for f in unfilled_m5_fvgs if f['type'] == -1 and f['top'] > current_price]
        if bearish_fvgs:
            valid_entry = min(bearish_fvgs, key=lambda x: x['bottom'])
            trade_dir = "Short"
            sl = valid_entry['top'] + 1

    if valid_entry:
        entry_p = current_price
        target = bias_info['dol'][1] if bias_info['dol'] else 0
        risk_pts = abs(entry_p - sl)
        pos_size = risk_per_trade / risk_pts if risk_pts > 0 else 0

        st.markdown(f"**Setup Detected:** {trade_dir}")
        st.markdown(f"**Entry:** {entry_p:.2f}")
        st.markdown(f"**Stop Loss:** {sl:.2f}")
        st.markdown(f"**Target:** {target:.2f}")
        st.markdown(f"**Position Size:** {pos_size:.2f} units")

        if st.button("EXECUTE ICT SETUP"):
            # Mock sending to QuantX
            st.success(f"Successfully routed order to QuantX (Topstep API) for {pos_size:.2f} units {trade_dir}!")
            st.balloons()
    else:
        st.warning("No valid FVG entry setup currently detected.")
        st.button("EXECUTE ICT SETUP", disabled=True)


# --- MAIN CONTENT AREA: VISUAL CHARTS ---

# Create Plotly Chart
# Only show the last N candles for clarity
plot_df = df_5m.tail(150).copy()

fig = go.Figure(data=[go.Candlestick(x=plot_df['Time'],
                open=plot_df['Open'],
                high=plot_df['High'],
                low=plot_df['Low'],
                close=plot_df['Close'],
                name="S&P 500")])

# Draw Midnight Open Line
if 'midnight_open' in po3_info:
    m_open = po3_info['midnight_open']
    fig.add_hline(y=m_open, line_dash="dash", line_color="orange",
                  annotation_text="Midnight Open", annotation_position="top right")

# Draw DOL Targets
if bias_info['dol']:
    dol_price = bias_info['dol'][1]
    dol_name = bias_info['dol'][0]
    fig.add_hline(y=dol_price, line_width=2, line_color="purple",
                  annotation_text=f"DOL: {dol_name}", annotation_position="bottom right")

# Highlight FVGs
# Filter to only show FVGs that overlap with our plot window
start_time = plot_df['Time'].iloc[0]
for fvg in m5_fvgs:
    fvg_time = fvg['time'] if fvg['time'] is not None else start_time
    if pd.to_datetime(fvg_time) >= start_time:
        color = "rgba(0, 255, 0, 0.2)" if fvg['type'] == 1 else "rgba(255, 0, 0, 0.2)"

        # Add shape for FVG
        fig.add_shape(type="rect",
            x0=fvg_time, y0=fvg['bottom'],
            x1=plot_df['Time'].iloc[-1], y1=fvg['top'],
            fillcolor=color,
            line=dict(color="rgba(255, 255, 255, 0)"),
            layer="below"
        )

# Format Chart
fig.update_layout(
    title='LiquidX 5-Minute Execution Chart',
    yaxis_title='Price',
    xaxis_title='Time',
    xaxis_rangeslider_visible=False,
    template='plotly_dark',
    height=700,
    margin=dict(l=0, r=0, t=40, b=0)
)

st.plotly_chart(fig, use_container_width=True)

# Footer info
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Current Price", f"{current_price:.2f}")
with col2:
    st.metric("PO3 Phase", po3_info.get('po3_phase', 'Unknown'))
with col3:
    st.metric("Latest Update", plot_df['Time'].iloc[-1].strftime('%Y-%m-%d %H:%M:%S'))
