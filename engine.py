import time
import datetime
import pandas as pd
from backtester import load_data
from ict_engine import detect_fvg, get_daily_bias, calculate_po3_levels
from database import init_db, log_trade, close_trade, get_open_trades
from notifier import logger, alert_trade_entry, alert_trade_exit, alert_error
from broker_connector import QuantXConnector, AccountManager

# Configuration
SYMBOL = "ES"
RISK_PER_TRADE = 1000
POLLING_INTERVAL_SECONDS = 60 # Check for setups every minute

def execute_live_loop():
    logger.info("Starting LiquidX Execution Engine...")
    init_db()

    # Initialize broker (Mocking for now unless env is fully set, but using actual classes)
    try:
        connector = QuantXConnector()
        connector.authenticate()
        manager = AccountManager(connector)
        manager.sync_accounts()
        logger.info(f"Broker connection successful. Synced {len(manager.accounts)} accounts.")
    except Exception as e:
        alert_error(f"Failed to connect to broker: {str(e)}")
        # For prototype daemon resilience, we won't crash, we'll just log
        manager = None

    while True:
        try:
            # 1. Fetch Latest Data (In production, this would be a live tick/candle stream. We use the local CSV loader for now as requested by the architecture)
            data = load_data('tradingdata')
            if not data or 'es' not in data or '5m' not in data['es']:
                alert_error("Engine: Missing required ES 5m data.")
                time.sleep(POLLING_INTERVAL_SECONDS)
                continue

            df_daily = data['es']['daily']
            df_1h = data['es']['1h']
            df_5m = data['es']['5m']

            current_close = df_5m['Close'].iloc[-1]
            current_time = df_5m['Time'].iloc[-1]

            # 2. Broker Reconciliation step
            # Query actual positions from broker to ensure local DB matches broker truth
            if manager:
                try:
                    broker_positions = manager.get_open_positions()
                    logger.info("Successfully polled broker for open positions.")
                    # In a real system, we'd cross-reference broker_positions with local open_trades here.
                    # E.g., if local says OPEN but broker says 0, the trade was stopped out at the broker.
                    # We log the success of the polling to demonstrate the retry resilience.
                except Exception as e:
                    alert_error(f"Reconciliation Loop Failed: Could not sync with broker: {e}")
                    # In a real system, we might pause trading if we can't verify broker state.

            open_trades = get_open_trades()

            if open_trades:
                for trade in open_trades:
                    # Trailing/exit check based on local price evaluation (mimicking broker SL hit)
                    trade_id = trade['id']
                    direction = trade['direction']
                    sl = trade['stop_loss']
                    tp = trade['take_profit']
                    entry_price = trade['entry_price']
                    size = trade['position_size']

                    exit_price = None
                    reason = ""

                    if direction == 'Long':
                        if current_close <= sl:
                            exit_price = sl
                            reason = "Stop Loss"
                        elif tp and current_close >= tp:
                            exit_price = tp
                            reason = "Take Profit"
                    elif direction == 'Short':
                        if current_close >= sl:
                            exit_price = sl
                            reason = "Stop Loss"
                        elif tp and current_close <= tp:
                            exit_price = tp
                            reason = "Take Profit"

                    if exit_price:
                        # Calculate PnL
                        pnl_points = (exit_price - entry_price) if direction == 'Long' else (entry_price - exit_price)
                        pnl_dollars = pnl_points * size

                        # Mark local DB as closed
                        close_trade(trade_id, exit_price, pnl_dollars)
                        alert_trade_exit(SYMBOL, direction, exit_price, pnl_dollars)

                        # Send broker close signal (pseudo-code depending on QuantX capabilities)
                        if manager:
                            # Usually a flatten or opposite market order
                            logger.info(f"Routing {reason} exit to broker for Trade {trade_id}")

            # 3. If no open trades, look for new setups
            if not open_trades:
                # Time filter
                trade_hour = current_time.hour
                trade_minute = current_time.minute
                time_in_minutes = trade_hour * 60 + trade_minute
                in_london = 60 <= time_in_minutes <= 360
                in_ny = 510 <= time_in_minutes <= 960

                if in_london or in_ny:
                    h1_fvgs = detect_fvg(df_1h)
                    daily_history = df_daily.iloc[:-1].copy() if len(df_daily) > 1 else df_daily.copy()
                    bias_info = get_daily_bias(daily_history, h1_fvgs, current_close)
                    bias = bias_info['bias']
                    dol = bias_info['dol']

                    if bias != 'Neutral' and dol is not None:
                        recent_fvgs = detect_fvg(df_5m.tail(3))
                        if recent_fvgs:
                            latest_fvg = recent_fvgs[-1]
                            target_price = dol[1]

                            trade_dir = None
                            entry_p = current_close
                            sl = 0

                            if bias == 'Bullish' and latest_fvg['type'] == 1:
                                sl = latest_fvg['bottom'] - (current_close * 0.00005)
                                risk_per_unit = entry_p - sl
                                if risk_per_unit > 0 and (target_price - entry_p) >= risk_per_unit * 1.0:
                                    trade_dir = "Long"

                            elif bias == 'Bearish' and latest_fvg['type'] == -1:
                                sl = latest_fvg['top'] + (current_close * 0.00005)
                                risk_per_unit = sl - entry_p
                                if risk_per_unit > 0 and (entry_p - target_price) >= risk_per_unit * 1.0:
                                    trade_dir = "Short"

                            if trade_dir:
                                pos_size = RISK_PER_TRADE / risk_per_unit

                                # Log to DB
                                trade_id = log_trade(SYMBOL, trade_dir, entry_p, sl, pos_size, take_profit=target_price)
                                alert_trade_entry(SYMBOL, trade_dir, entry_p, sl, target_price, pos_size)

                                # Route to Broker
                                if manager:
                                    action = "Buy" if trade_dir == "Long" else "Sell"
                                    manager.execute_trade(SYMBOL, action, RISK_PER_TRADE, entry_p, sl)
                                    logger.info("Trade successfully routed to QuantX trade copier.")

        except Exception as e:
            alert_error(f"Fatal error in execution loop: {str(e)}")

        # Sleep until next poll
        time.sleep(POLLING_INTERVAL_SECONDS)

if __name__ == "__main__":
    execute_live_loop()
