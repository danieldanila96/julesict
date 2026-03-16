import pandas as pd
from ict_engine import detect_fvg, get_daily_bias, calculate_po3_levels

def test_logic():
    print("Testing ict_engine.py logic...")

    # Load 60min data
    df_60m = pd.read_csv('tradingdata/spx_intraday-60min_historical-data-03-04-2026.csv')

    # Clean up bottom row if it contains metadata
    df_60m = df_60m[~df_60m['Time'].str.contains('Downloaded', na=False)]

    df_60m['Time'] = pd.to_datetime(df_60m['Time'])
    df_60m = df_60m.sort_values('Time').reset_index(drop=True)

    # 1. Detect FVGs
    print("\n--- detect_fvg ---")
    fvgs = detect_fvg(df_60m)
    print(f"Detected {len(fvgs)} FVGs.")
    unfilled = [f for f in fvgs if not f['filled']]
    print(f"Unfilled FVGs: {len(unfilled)}")

    # 2. Get Daily Bias
    print("\n--- get_daily_bias ---")
    # For a real implementation we'd use daily data, but for this test we'll use a resampled daily df
    df_daily = df_60m.set_index('Time').resample('D').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Latest': 'last'
    }).dropna().reset_index()

    current_price = df_60m['Latest'].iloc[-1]
    bias_info = get_daily_bias(df_daily, fvgs, current_price)
    print(f"Bias: {bias_info['bias']}")
    print(f"DOL: {bias_info['dol']}")
    print(f"Targets Above: {len(bias_info['targets_above'])}")
    print(f"Targets Below: {len(bias_info['targets_below'])}")

    # 3. Calculate PO3 Levels
    print("\n--- calculate_po3_levels ---")
    po3_info = calculate_po3_levels(df_60m, bias=bias_info['bias'])
    print(f"Midnight Open: {po3_info.get('midnight_open')}")
    print(f"Current Price: {po3_info.get('current_price')}")
    print(f"PO3 Phase: {po3_info.get('po3_phase')}")

if __name__ == '__main__':
    test_logic()