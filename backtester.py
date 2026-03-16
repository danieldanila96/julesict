import pandas as pd
import numpy as np
import os
import glob
from ict_engine import detect_fvg, get_daily_bias, calculate_po3_levels
from config_manager import load_profile

def load_data(folder_path='tradingdata'):
    data = {'es': {}, 'nq': {}, 'ym': {}}
    import glob
    import os
    import pandas as pd
    files = glob.glob(os.path.join(folder_path, '*.csv'))
    for file in files:
        df = pd.read_csv(file)
        df = df[~df['Time'].astype(str).str.contains('Downloaded', na=False, case=False)].copy()
        df['Time'] = pd.to_datetime(df['Time'])
        df = df.sort_values('Time').reset_index(drop=True)
        if 'Latest' in df.columns and 'Close' not in df.columns:
            df['Close'] = df['Latest']
        filename = os.path.basename(file).lower()
        instrument = None
        if filename.startswith('spx_'):
            instrument = 'es'
        elif filename.startswith('nqh26_'):
            instrument = 'nq'
        elif filename.startswith('ymh26_'):
            instrument = 'ym'

        if instrument:
            if '60min' in filename:
                data[instrument]['1h'] = df
            elif '5min' in filename:
                data[instrument]['5m'] = df
            elif 'daily' in filename:
                data[instrument]['daily'] = df

    for inst in data:
        if '1h' in data[inst] and 'daily' not in data[inst]:
            df_1h = data[inst]['1h'].copy()
            df_daily = df_1h.set_index('Time').resample('D').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
            }).dropna().reset_index()
            data[inst]['daily'] = df_daily
    return data

def run_backtest(profile_name=None):
    """
    Runs a historical backtest of the ICT strategy using parameters loaded from config.
    """
    config = load_profile(profile_name)
    initial_capital = config.get("Backtest", {}).get("initial_capital", 100000)
    risk_per_trade = config.get("Risk", {}).get("risk_per_trade_usd", 1000)
    slippage = config.get("Backtest", {}).get("slippage", 0.25)
    commission = config.get("Backtest", {}).get("commission", 2.0)
    point_value = config.get("Risk", {}).get("point_value", 50.0)

    # Strategy controls
    min_rr = config.get("Strategy", {}).get("min_rr", 1.2)
    fvg_buffer = config.get("Strategy", {}).get("fvg_buffer_pct", 0.001)

    # Market controls
    target_symbol = config.get("Market", {}).get("symbol", "es")
    ltf = config.get("Market", {}).get("timeframe", "5m")
    htf = config.get("Market", {}).get("htf", "1h")

    # Time filters
    london_start = config.get("Market", {}).get("london_start", 60)
    london_end = config.get("Market", {}).get("london_end", 360)
    ny_start = config.get("Market", {}).get("ny_start", 510)
    ny_end = config.get("Market", {}).get("ny_end", 960)

    print(f"Loading data for backtest using profile '{profile_name}'...")
    data = load_data()

    if target_symbol not in data or ltf not in data[target_symbol] or htf not in data[target_symbol] or 'daily' not in data[target_symbol]:
        err_msg = f"Error: Missing required timeframes (Daily, {htf.upper()}, {ltf.upper()}) for {target_symbol.upper()} in tradingdata folder."
        print(err_msg)
        return {"error": err_msg}

    df_daily = data[target_symbol]['daily']
    df_1h = data[target_symbol][htf]
    df_5m = data[target_symbol][ltf]

    # Filter data based on Start / End Dates if set in config
    start_str = config.get("Backtest", {}).get("start_date")
    end_str = config.get("Backtest", {}).get("end_date")

    if start_str and end_str:
        start_date = pd.to_datetime(start_str).date()
        end_date = pd.to_datetime(end_str).date()
        df_5m = df_5m[(df_5m['Time'].dt.date >= start_date) & (df_5m['Time'].dt.date <= end_date)]

    print(f"Loaded: {len(df_daily)} daily candles, {len(df_1h)} {htf.upper()} candles, {len(df_5m)} {ltf.upper()} candles.")

    capital = initial_capital
    trades = []

    # We'll step through the 5m data day by day
    # Group 5m data by date
    df_5m['Date'] = df_5m['Time'].dt.date
    unique_dates = df_5m['Date'].unique()

    print("\nStarting simulation...")

    # Only iterate through dates where we have enough historical data
    # (e.g., skip the first few days so we have daily/1h context)

    for date in unique_dates[5:]:

        # 1. Get Context up to the START of this day
        # Filter Daily and 1H data strictly BEFORE this date to avoid lookahead bias
        daily_history = df_daily[df_daily['Time'].dt.date < date].copy()
        h1_history = df_1h[df_1h['Time'].dt.date < date].copy()

        if len(daily_history) < 2 or len(h1_history) < 20:
            continue

        # Get 1H FVGs (used for higher timeframe targets)
        h1_fvgs = detect_fvg(h1_history)

        # Get Daily Bias based on yesterday's close
        yesterday_close = daily_history['Close'].iloc[-1]
        bias_info = get_daily_bias(daily_history, h1_fvgs, yesterday_close)
        bias = bias_info['bias']
        dol = bias_info['dol']

        if bias == 'Neutral' or dol is None:
            continue # Skip days without a clear bias

        # 2. Process the Intraday Action (5M candles)
        day_data = df_5m[df_5m['Date'] == date].copy().reset_index(drop=True)
        if day_data.empty:
            continue

        # Initialize day tracking
        in_trade = False
        entry_price = 0
        stop_loss = 0
        take_profit = dol[1] # Target is the DOL
        position_size = 0
        trade_dir = 1 if bias == 'Bullish' else -1
        manipulation_seen = False

        # Iterate through the day's 5M candles
        for i in range(2, len(day_data)):
            current_time = day_data['Time'].iloc[i]
            current_close = day_data['Close'].iloc[i]
            current_high = day_data['High'].iloc[i]
            current_low = day_data['Low'].iloc[i]

            # Update PO3 phase
            # For backtesting mid-day, we pass data up to the current candle
            current_history = day_data.iloc[:i+1]
            po3_info = calculate_po3_levels(current_history, bias=bias)

            if po3_info.get('error'):
                continue

            phase = po3_info.get('po3_phase')

            if not in_trade:
                # Track if manipulation has occurred
                if phase == 'Manipulation (Judas Swing)':
                    manipulation_seen = True

                # Look for entry if manipulation has occurred and we are moving towards distribution
                if True: # Relaxed PO3 manipulation requirement to increase trades
                    # Look for a fresh 5M FVG in the direction of our bias
                    # We check the last 3 candles: i-2, i-1, i
                    recent_3_candles = day_data.iloc[i-2:i+1].copy()
                    recent_fvgs = detect_fvg(recent_3_candles)

                    if recent_fvgs:
                        latest_fvg = recent_fvgs[-1]

                        # Add Time Filter (London & NY Killzones)
                        trade_hour = current_time.hour
                        trade_minute = current_time.minute
                        time_in_minutes = trade_hour * 60 + trade_minute

                        in_london = london_start <= time_in_minutes <= london_end
                        in_ny = ny_start <= time_in_minutes <= ny_end

                        if not (in_london or in_ny):
                            continue

                        # Enter Long
                        if bias == 'Bullish' and latest_fvg['type'] == 1:
                            entry_price = current_close + slippage
                            stop_loss = latest_fvg['bottom'] - (current_close * fvg_buffer)

                            risk_per_unit = entry_price - stop_loss
                            if risk_per_unit <= 0:
                                continue

                            reward_per_unit = take_profit - entry_price
                            if reward_per_unit < risk_per_unit * min_rr:
                                continue

                            in_trade = True
                            position_size = risk_per_trade / risk_per_unit

                        # Enter Short
                        elif bias == 'Bearish' and latest_fvg['type'] == -1:
                            entry_price = current_close - slippage
                            stop_loss = latest_fvg['top'] + (current_close * fvg_buffer)

                            risk_per_unit = stop_loss - entry_price
                            if risk_per_unit <= 0:
                                continue

                            reward_per_unit = entry_price - take_profit
                            if reward_per_unit < risk_per_unit * min_rr:
                                continue

                            in_trade = True
                            position_size = risk_per_trade / risk_per_unit

            else:
                # We are in a trade, check for exit (Stop Loss or Take Profit)
                exit_price = 0
                exit_reason = ""

                if trade_dir == 1: # Long
                    if current_low <= stop_loss:
                        exit_price = stop_loss - slippage
                        exit_reason = "Stop Loss"
                    elif current_high >= take_profit:
                        exit_price = take_profit - slippage
                        exit_reason = "Take Profit"
                else: # Short
                    if current_high >= stop_loss:
                        exit_price = stop_loss + slippage
                        exit_reason = "Stop Loss"
                    elif current_low <= take_profit:
                        exit_price = take_profit + slippage
                        exit_reason = "Take Profit"

                # End of day exit
                if i == len(day_data) - 1 and not exit_reason:
                    if trade_dir == 1:
                        exit_price = current_close - slippage
                    else:
                        exit_price = current_close + slippage
                    exit_reason = "End of Day"

                if exit_reason:
                    # Point value multiplier should technically be used here (e.g. $50 for ES), but
                    # we are calculating based on purely points. Assuming 1 contract for simplicity of units.
                    pnl = (exit_price - entry_price) * position_size * trade_dir

                    # Deduct commissions
                    # position_size represents total point distance risk.
                    # Converting to standard contracts:
                    contracts = position_size / point_value
                    total_commission = contracts * commission * 2 # round trip
                    pnl -= total_commission

                    capital += pnl

                    trades.append({
                        'Date': date,
                        'Type': 'Long' if trade_dir == 1 else 'Short',
                        'Entry Time': current_time, # approximate entry time based on 5m candle close
                        'Entry Price': entry_price,
                        'Exit Price': exit_price,
                        'Stop Loss': stop_loss,
                        'Take Profit': take_profit,
                        'PnL': pnl,
                        'Reason': exit_reason,
                        'Capital': capital
                    })

                    in_trade = False
                    # Max 1 trade per day for this simple model
                    #break # allow multiple trades per day

    # --- Print Summary ---
    # Calculate statistics to return to UI
    if not trades:
        return {"error": "No trades executed during the backtest."}

    df_trades = pd.DataFrame(trades)
    df_trades['Cumulative Equity'] = df_trades['Capital']

    total_trades = len(df_trades)
    winning_trades = len(df_trades[df_trades['PnL'] > 0])
    losing_trades = len(df_trades[df_trades['PnL'] <= 0])
    win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

    gross_profit = df_trades[df_trades['PnL'] > 0]['PnL'].sum()
    gross_loss = abs(df_trades[df_trades['PnL'] < 0]['PnL'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    total_pnl = df_trades['PnL'].sum()
    final_capital = initial_capital + total_pnl
    return_pct = (total_pnl / initial_capital) * 100

    # Save a copy as CSV
    import datetime
    os.makedirs('reports', exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_base = f"reports/backtest_{timestamp}.csv"
    df_trades.to_csv(report_base, index=False)

    return {
        "trades": df_trades,
        "stats": {
            "initial_capital": initial_capital,
            "final_capital": final_capital,
            "total_pnl": total_pnl,
            "return_pct": return_pct,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "profit_factor": profit_factor,
            "risk_per_trade": risk_per_trade
        }
    }


if __name__ == '__main__':
    run_backtest()
