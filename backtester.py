import pandas as pd
import numpy as np
import os
import glob
from ict_engine import detect_fvg, get_daily_bias, calculate_po3_levels

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

def run_backtest(initial_capital=100000, risk_per_trade=1000):
    """
    Runs a simplified historical backtest of the ICT strategy.

    Strategy Rules:
    1. Daily Bias (from daily data & 1H FVGs): Determine Draw on Liquidity (DOL).
    2. Midnight Open (PO3): Wait for manipulation (Judas Swing) in the opposite direction of bias.
    3. Entry: Enter when price forms an FVG on the 5-min timeframe in the direction of the bias,
       after manipulation has occurred.
    4. Exit: Target is the DOL. Stop loss is below the 5-min FVG or recent swing low/high.
    """

    print("Loading data for backtest...")
    data = load_data()

    if 'es' not in data or '5m' not in data['es'] or '1h' not in data['es'] or 'daily' not in data['es']:
        print("Error: Missing required timeframes (Daily, 1H, 5M) for ES in tradingdata folder.")
        return

    df_daily = data['es']['daily']
    df_1h = data['es']['1h']
    df_5m = data['es']['5m']

    print(f"Loaded: {len(df_daily)} daily candles, {len(df_1h)} 1H candles, {len(df_5m)} 5M candles.")

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

                        # London Killzone: 3:00 AM - 6:00 AM (180 to 360 mins)
                        # NY Killzone: 8:30 AM - 12:00 PM (510 to 720 mins)
                        in_london = 60 <= time_in_minutes <= 360
                        in_ny = 510 <= time_in_minutes <= 960

                        if not (in_london or in_ny):
                            continue

                        # Enter Long
                        if bias == 'Bullish' and latest_fvg['type'] == 1:
                            entry_price = current_close
                            stop_loss = latest_fvg['bottom'] - (current_close * 0.001) # 0.1% Buffer below FVG

                            # Simple risk calc: R = entry - sl
                            risk_per_unit = entry_price - stop_loss
                            if risk_per_unit <= 0:
                                continue

                            reward_per_unit = take_profit - entry_price
                            # Minimum 1:1.2 Risk to Reward
                            if reward_per_unit < risk_per_unit * 1.2:
                                continue

                            in_trade = True
                            position_size = risk_per_trade / risk_per_unit

                        # Enter Short
                        elif bias == 'Bearish' and latest_fvg['type'] == -1:
                            entry_price = current_close
                            stop_loss = latest_fvg['top'] + (current_close * 0.001) # 0.1% Buffer above FVG

                            # Simple risk calc
                            risk_per_unit = stop_loss - entry_price
                            if risk_per_unit <= 0:
                                continue

                            reward_per_unit = entry_price - take_profit
                            # Minimum 1:1.2 Risk to Reward
                            if reward_per_unit < risk_per_unit * 1.2:
                                continue

                            in_trade = True
                            position_size = risk_per_trade / risk_per_unit

            else:
                # We are in a trade, check for exit (Stop Loss or Take Profit)
                exit_price = 0
                exit_reason = ""

                if trade_dir == 1: # Long
                    if current_low <= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "Stop Loss"
                    elif current_high >= take_profit:
                        exit_price = take_profit
                        exit_reason = "Take Profit"
                else: # Short
                    if current_high >= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "Stop Loss"
                    elif current_low <= take_profit:
                        exit_price = take_profit
                        exit_reason = "Take Profit"

                # End of day exit
                if i == len(day_data) - 1 and not exit_reason:
                    exit_price = current_close
                    exit_reason = "End of Day"

                if exit_reason:
                    pnl = (exit_price - entry_price) * position_size * trade_dir
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
    print("\n" + "="*40)
    print("BACKTEST SUMMARY")
    print("="*40)

    if not trades:
        print("No trades taken during the period.")
        return

    df_trades = pd.DataFrame(trades)

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

    print(f"Total Trades:   {total_trades}")
    print(f"Win Rate:       {win_rate:.2f}% ({winning_trades} W / {losing_trades} L)")
    print(f"Profit Factor:  {profit_factor:.2f}")
    print(f"Starting Cap:   ${initial_capital:,.2f}")
    print(f"Final Cap:      ${final_capital:,.2f}")
    print(f"Total Net PnL:  ${total_pnl:,.2f} ({return_pct:.2f}%)")
    print("="*40)

    print("\nLast 5 Trades:")
    print(df_trades[['Date', 'Type', 'Entry Price', 'Exit Price', 'PnL', 'Reason']].tail())

    # Generate Reports
    import datetime
    import plotly.graph_objects as go

    os.makedirs('reports', exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_base = f"reports/backtest_{timestamp}"

    # Save raw trades for Streamlit to ingest easily
    df_trades['Cumulative Equity'] = df_trades['Capital']
    df_trades.to_csv(f"{report_base}.csv", index=False)

    # Save a standalone HTML report
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_trades['Date'], y=df_trades['Cumulative Equity'], mode='lines', name='Equity Curve'))

    fig.update_layout(
        title=f"LiquidX Backtest Report - {timestamp}",
        xaxis_title="Date",
        yaxis_title="Account Equity ($)",
        template='plotly_dark'
    )

    # Convert dataframe to HTML table
    table_html = df_trades[['Date', 'Type', 'Entry Price', 'Exit Price', 'PnL', 'Cumulative Equity', 'Reason']].to_html(classes='table table-striped', index=False)

    html_content = f"""
    <html>
    <head>
        <title>LiquidX Backtest - {timestamp}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #121212; color: #ffffff; }}
            .summary {{ padding: 20px; background-color: #1e1e1e; border-radius: 8px; margin-bottom: 20px; }}
            .table-container {{ overflow-x: auto; margin-top: 30px; }}
            table {{ width: 100%; border-collapse: collapse; text-align: left; }}
            th, td {{ padding: 12px; border-bottom: 1px solid #333; }}
            th {{ background-color: #2c2c2c; }}
        </style>
        <!-- DataTables CSS/JS for sortable HTML tables -->
        <link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
        <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
        <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
        <script>
            $(document).ready( function () {{
                $('.table').DataTable({{
                    "pageLength": 50,
                    "order": [[ 0, "desc" ]] // sort by date descending
                }});
            }} );
        </script>
    </head>
    <body>
        <h1>LiquidX Backtest Report</h1>
        <div class="summary">
            <h2>Summary Statistics</h2>
            <p><strong>Starting Capital:</strong> ${initial_capital:,.2f}</p>
            <p><strong>Risk Per Trade:</strong> ${risk_per_trade:,.2f}</p>
            <p><strong>Total Trades:</strong> {total_trades}</p>
            <p><strong>Win Rate:</strong> {win_rate:.2f}% ({winning_trades}W / {losing_trades}L)</p>
            <p><strong>Profit Factor:</strong> {profit_factor:.2f}</p>
            <p><strong>Final Capital:</strong> ${final_capital:,.2f}</p>
            <p><strong>Total Net PnL:</strong> ${total_pnl:,.2f} ({return_pct:.2f}%)</p>
        </div>

        <div style="height: 500px; width: 100%;">
            {fig.to_html(full_html=False, include_plotlyjs='cdn')}
        </div>

        <div class="table-container">
            <h2>Trade Log</h2>
            {table_html}
        </div>
    </body>
    </html>
    """

    with open(f"{report_base}.html", "w") as f:
        f.write(html_content)

    print(f"\nReport generated: {report_base}.html and {report_base}.csv")


if __name__ == '__main__':
    run_backtest()
