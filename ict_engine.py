import pandas as pd
import numpy as np

def detect_fvg(df):
    """
    Detects Fair Value Gaps (FVGs) and Inverted FVGs in a DataFrame.
    A Fair Value Gap is a 3-candle sequence where Candle 1 and 3 wicks do not overlap.
    Includes 'Inverted FVG' logic: if price closes through a bearish FVG, it becomes a bullish support zone,
    and vice versa.

    Args:
        df: pd.DataFrame with columns ['Time', 'Open', 'High', 'Low', 'Close'] or 'Latest'
            Assumed to be sorted by Time ascending.

    Returns:
        list of dicts containing active FVGs and their status.
    """
    df = df.copy()
    if 'Close' not in df.columns and 'Latest' in df.columns:
        df['Close'] = df['Latest']

    active_fvgs = []

    # Needs a loop to identify 3-candle patterns and check for fills/inversions
    for i in range(2, len(df)):
        # 1. Check for Bullish FVG
        # Low of candle 3 > High of candle 1
        low_c3 = df['Low'].iloc[i]
        high_c1 = df['High'].iloc[i-2]
        if low_c3 > high_c1:
            active_fvgs.append({
                'type': 1, # 1 for bullish
                'top': low_c3,
                'bottom': high_c1,
                'start_idx': i-2,
                'end_idx': i,
                'time': df['Time'].iloc[i-2] if 'Time' in df.columns else None,
                'is_inverted': False,
                'filled': False
            })

        # 2. Check for Bearish FVG
        # High of candle 3 < Low of candle 1
        high_c3 = df['High'].iloc[i]
        low_c1 = df['Low'].iloc[i-2]
        if high_c3 < low_c1:
            active_fvgs.append({
                'type': -1, # -1 for bearish
                'top': low_c1,
                'bottom': high_c3,
                'start_idx': i-2,
                'end_idx': i,
                'time': df['Time'].iloc[i-2] if 'Time' in df.columns else None,
                'is_inverted': False,
                'filled': False
            })

        # 3. Check for fills and inversions on existing active FVGs
        close_price = df['Close'].iloc[i]
        for fvg in active_fvgs:
            if not fvg['filled']:
                if fvg['type'] == 1:  # Bullish
                    # Check if filled/inverted (price closes below bottom)
                    if close_price < fvg['bottom']:
                        fvg['is_inverted'] = True
                        fvg['type'] = -1  # Now acts as bearish resistance
                        fvg['filled'] = True
                elif fvg['type'] == -1:  # Bearish
                    # Check if filled/inverted (price closes above top)
                    if close_price > fvg['top']:
                        fvg['is_inverted'] = True
                        fvg['type'] = 1   # Now acts as bullish support
                        fvg['filled'] = True

    return active_fvgs


def get_daily_bias(df_daily, fvgs, current_price):
    """
    Determines 'Draw on Liquidity' (DOL) by identifying nearest unfilled FVGs
    and previous daily highs/lows.

    Args:
        df_daily: pd.DataFrame with daily timeframe data.
        fvgs: List of active FVGs from `detect_fvg` (usually from daily or 1-hour).
        current_price: Float, current market price.

    Returns:
        dict: containing bias direction and nearest targets (DOL).
    """
    df = df_daily.copy()
    if 'Close' not in df.columns and 'Latest' in df.columns:
        df['Close'] = df['Latest']

    # Get previous daily high and low
    # Assuming the df_daily passed has already been filtered to exclude the current unclosed day.
    # Therefore, the last row is the previous day.
    if len(df) >= 1:
        prev_day_high = df['High'].iloc[-1]
        prev_day_low = df['Low'].iloc[-1]
    else:
        prev_day_high = None
        prev_day_low = None

    # Find nearest unfilled FVGs above and below
    unfilled_fvgs = [f for f in fvgs if not f['filled']]

    fvgs_above = [f for f in unfilled_fvgs if f['bottom'] > current_price]
    fvgs_below = [f for f in unfilled_fvgs if f['top'] < current_price]

    nearest_fvg_above = min(fvgs_above, key=lambda x: x['bottom']) if fvgs_above else None
    nearest_fvg_below = max(fvgs_below, key=lambda x: x['top']) if fvgs_below else None

    targets_above = []
    if prev_day_high and prev_day_high > current_price:
        targets_above.append(('PDH (Previous Daily High)', prev_day_high))
    if nearest_fvg_above:
        targets_above.append(('Unfilled FVG Above', nearest_fvg_above['bottom']))

    targets_below = []
    if prev_day_low and prev_day_low < current_price:
        targets_below.append(('PDL (Previous Daily Low)', prev_day_low))
    if nearest_fvg_below:
        targets_below.append(('Unfilled FVG Below', nearest_fvg_below['top']))

    # Sort targets by distance from current price
    targets_above.sort(key=lambda x: x[1])
    targets_below.sort(key=lambda x: x[1], reverse=True)

    dol_up = targets_above[0] if targets_above else None
    dol_down = targets_below[0] if targets_below else None

    bias = 'Neutral'
    dol = None

    # Simple bias logic: Draw on Liquidity is the closest target
    if dol_up and dol_down:
        dist_up = dol_up[1] - current_price
        dist_down = current_price - dol_down[1]

        # In a more advanced implementation, bias might also rely on market structure (higher highs, etc.)
        if dist_up < dist_down:
            bias = 'Bullish'
            dol = dol_up
        else:
            bias = 'Bearish'
            dol = dol_down
    elif dol_up:
        bias = 'Bullish'
        dol = dol_up
    elif dol_down:
        bias = 'Bearish'
        dol = dol_down

    return {
        'bias': bias,
        'dol': dol,
        'targets_above': targets_above,
        'targets_below': targets_below
    }


def calculate_po3_levels(df_intraday, bias=None, midnight_hour=0, midnight_minute=0):
    """
    Tracks the 'Midnight Open' price (00:00 EST).
    Looks for 'Accumulation' at open, 'Manipulation', and 'Distribution'.

    Args:
        df_intraday: pd.DataFrame with intraday data (e.g., 5-min or 1-hour).
                     Must have 'Time' column parsed or parsable as datetime.
        bias: The daily bias ('Bullish', 'Bearish', or 'Neutral').
        midnight_hour: The hour representing Midnight Open.
        midnight_minute: The minute representing Midnight Open.

    Returns:
        dict: containing Midnight Open price and current PO3 phase.
    """
    df = df_intraday.copy()
    if 'Time' not in df.columns:
        return {'error': 'No Time column in DataFrame.'}

    # Ensure Time is datetime
    df['Time'] = pd.to_datetime(df['Time'])

    if len(df) == 0:
        return {'error': 'DataFrame is empty.'}

    # Find Midnight Open
    # Get the latest day's midnight open
    latest_date = df['Time'].dt.date.iloc[-1]

    # Filter for the latest day's midnight time
    midnight_data = df[(df['Time'].dt.date == latest_date) &
                       (df['Time'].dt.hour == midnight_hour) &
                       (df['Time'].dt.minute == midnight_minute)]

    if midnight_data.empty:
        # If exact minute isn't there, get the first candle of the day
        midnight_data = df[df['Time'].dt.date == latest_date].sort_values('Time').head(1)

    if midnight_data.empty:
        return {'error': 'No data for the current day.'}

    midnight_open = midnight_data['Open'].iloc[0]

    if 'Close' not in df.columns and 'Latest' in df.columns:
        current_price = df['Latest'].iloc[-1]
    else:
        current_price = df['Close'].iloc[-1]

    # Analyze PO3 phase (Accumulation, Manipulation, Distribution)
    # Simple heuristics:
    # Accumulation: Price near midnight open
    # Manipulation: Move against bias (Bullish bias -> move below open; Bearish bias -> move above open)
    # Distribution: Move in direction of bias

    # Approximate recent volatility
    recent_high = df['High'].iloc[-10:].max()
    recent_low = df['Low'].iloc[-10:].min()
    atr_approx = recent_high - recent_low if recent_high != recent_low else current_price * 0.001

    distance_from_open = abs(current_price - midnight_open)

    phase = 'Unknown'

    if distance_from_open < atr_approx * 0.2:
        phase = 'Accumulation'
    elif bias == 'Bullish':
        if current_price < midnight_open:
            phase = 'Manipulation (Judas Swing)'
        elif current_price > midnight_open:
            phase = 'Distribution'
    elif bias == 'Bearish':
        if current_price > midnight_open:
            phase = 'Manipulation (Judas Swing)'
        elif current_price < midnight_open:
            phase = 'Distribution'
    else:
        phase = 'Expansion (No strong bias defined)'

    return {
        'midnight_open': midnight_open,
        'current_price': current_price,
        'po3_phase': phase
    }


def detect_smt_divergence(df_es, df_nq, df_ym, lookback=10):
    """
    Compares NQ, ES, and YM for relative strength (SMT) divergence.

    If NQ makes a lower low but ES doesn't, flag a bullish SMT divergence.
    If NQ makes a higher high but ES doesn't, flag a bearish SMT divergence.

    Args:
        df_es: pd.DataFrame of ES (S&P500) data.
        df_nq: pd.DataFrame of NQ (Nasdaq) data.
        df_ym: pd.DataFrame of YM (Dow Jones) data.
        lookback: Integer, number of recent periods to compare for swing highs/lows.

    Returns:
        dict: containing the SMT status and a descriptive message.
    """
    if len(df_es) < lookback or len(df_nq) < lookback or len(df_ym) < lookback:
        return {'status': 'None', 'message': 'Insufficient data'}

    # Get recent slice
    es_recent = df_es.iloc[-lookback:].copy()
    nq_recent = df_nq.iloc[-lookback:].copy()
    ym_recent = df_ym.iloc[-lookback:].copy()

    # Simple Swing High/Low approximation (min/max of the lookback period)
    es_low = es_recent['Low'].min()
    nq_low = nq_recent['Low'].min()
    ym_low = ym_recent['Low'].min()

    es_high = es_recent['High'].max()
    nq_high = nq_recent['High'].max()
    ym_high = ym_recent['High'].max()

    # We also need a prior reference point to establish if it's a "lower low" vs "higher low"
    # We take the preceding lookback period
    if len(df_es) >= lookback * 2:
        es_prior = df_es.iloc[-lookback*2:-lookback]
        nq_prior = df_nq.iloc[-lookback*2:-lookback]
        ym_prior = df_ym.iloc[-lookback*2:-lookback]

        es_prior_low = es_prior['Low'].min()
        nq_prior_low = nq_prior['Low'].min()
        ym_prior_low = ym_prior['Low'].min()

        es_prior_high = es_prior['High'].max()
        nq_prior_high = nq_prior['High'].max()
        ym_prior_high = ym_prior['High'].max()
    else:
        # If not enough history, use the first half of the available lookback as prior
        mid = lookback // 2
        es_prior_low = es_recent['Low'].iloc[:mid].min()
        nq_prior_low = nq_recent['Low'].iloc[:mid].min()
        ym_prior_low = ym_recent['Low'].iloc[:mid].min()

        es_prior_high = es_recent['High'].iloc[:mid].max()
        nq_prior_high = nq_recent['High'].iloc[:mid].max()
        ym_prior_high = ym_recent['High'].iloc[:mid].max()

        es_low = es_recent['Low'].iloc[mid:].min()
        nq_low = nq_recent['Low'].iloc[mid:].min()
        ym_low = ym_recent['Low'].iloc[mid:].min()

        es_high = es_recent['High'].iloc[mid:].max()
        nq_high = nq_recent['High'].iloc[mid:].max()
        ym_high = ym_recent['High'].iloc[mid:].max()

    # Determine structural swings
    es_made_ll = es_low < es_prior_low
    nq_made_ll = nq_low < nq_prior_low
    ym_made_ll = ym_low < ym_prior_low

    es_made_hh = es_high > es_prior_high
    nq_made_hh = nq_high > nq_prior_high
    ym_made_hh = ym_high > ym_prior_high

    status = "None"
    message = "Indices in sync"

    # Bullish SMT Divergence Checks
    # E.g., NQ makes Lower Low, but ES makes Higher Low
    bullish_smt = False
    bullish_msgs = []

    if nq_made_ll and not es_made_ll:
        bullish_smt = True
        bullish_msgs.append("NQ Lower Low / ES Higher Low")
    if es_made_ll and not nq_made_ll:
        bullish_smt = True
        bullish_msgs.append("ES Lower Low / NQ Higher Low")
    if ym_made_ll and not es_made_ll:
        bullish_smt = True
        bullish_msgs.append("YM Lower Low / ES Higher Low")

    # Bearish SMT Divergence Checks
    # E.g., NQ makes Higher High, but ES makes Lower High
    bearish_smt = False
    bearish_msgs = []

    if nq_made_hh and not es_made_hh:
        bearish_smt = True
        bearish_msgs.append("NQ Higher High / ES Lower High")
    if es_made_hh and not nq_made_hh:
        bearish_smt = True
        bearish_msgs.append("ES Higher High / NQ Lower High")
    if ym_made_hh and not es_made_hh:
        bearish_smt = True
        bearish_msgs.append("YM Higher High / ES Lower High")

    if bullish_smt and bearish_smt:
        status = "Mixed Divergence"
        message = "Conflicting SMT signals"
    elif bullish_smt:
        status = "Bullish SMT"
        message = " | ".join(bullish_msgs)
    elif bearish_smt:
        status = "Bearish SMT"
        message = " | ".join(bearish_msgs)

    return {
        'status': status,
        'message': message,
        'es_low': es_low, 'nq_low': nq_low, 'ym_low': ym_low,
        'es_high': es_high, 'nq_high': nq_high, 'ym_high': ym_high
    }
