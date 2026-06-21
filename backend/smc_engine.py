import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Any

def detect_swing_points(df: pd.DataFrame, N: int = 2) -> pd.DataFrame:
    """
    Identifies swing highs/lows by lookback/lookahead window N.
    A candle is a swing high if its high is greater than the highs of N candles before and N candles after.
    A candle is a swing low if its low is lower than the lows of N candles before and N candles after.
    """
    df = df.copy()
    df['is_swing_high'] = False
    df['is_swing_low'] = False
    df['swing_high_val'] = np.nan
    df['swing_low_val'] = np.nan

    highs = df['high'].values
    lows = df['low'].values
    length = len(df)

    for i in range(N, length - N):
        # Swing High check
        val_h = highs[i]
        is_sh = True
        for j in range(i - N, i + N + 1):
            if j != i and highs[j] >= val_h:
                is_sh = False
                break
        if is_sh:
            df.at[df.index[i], 'is_swing_high'] = True
            df.at[df.index[i], 'swing_high_val'] = val_h

        # Swing Low check
        val_l = lows[i]
        is_sl = True
        for j in range(i - N, i + N + 1):
            if j != i and lows[j] <= val_l:
                is_sl = False
                break
        if is_sl:
            df.at[df.index[i], 'is_swing_low'] = True
            df.at[df.index[i], 'swing_low_val'] = val_l

    return df

def calculate_smc(df: pd.DataFrame, N: int = 2, X_impulse: float = 2.0, M_range: int = 5) -> Dict[str, Any]:
    """
    Computes all Smart Money Concepts details on the OHLC data.
    Returns calculated lists and structures:
    - swing_highs, swing_lows
    - bos (list of dicts)
    - choch (list of dicts)
    - supply_zones, demand_zones
    - fvgs
    - liquidity_grabs
    - trend (list of trends per candle)
    """
    df = detect_swing_points(df, N)
    
    # Calculate average candle range for impulse filtering
    df['candle_range'] = df['high'] - df['low']
    df['avg_range'] = df['candle_range'].rolling(window=M_range).mean()
    
    # Calculate average wick size for liquidity grab filtering
    df['high_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['low_wick'] = df[['open', 'close']].min(axis=1) - df['low']
    df['avg_high_wick'] = df['high_wick'].rolling(window=10).mean()
    df['avg_low_wick'] = df['low_wick'].rolling(window=10).mean()

    # Trackers for structure
    trend = "neutral"
    last_sh_idx = -1
    last_sh_val = np.nan
    last_sl_idx = -1
    last_sl_val = np.nan
    
    # Keep historical swings
    swing_highs = [] # list of (idx, val)
    swing_lows = []  # list of (idx, val)

    bos_list = []
    choch_list = []
    
    # Structure states for trend classification (HH, HL, LL, LH)
    # To determine uptrend: last two swings are HH and HL
    # To determine downtrend: last two swings are LL and LH
    swings_history = [] # list of dict: {type: 'SH'/'SL', idx: int, price: float, label: 'HH'/'HL'/'LL'/'LH'}

    # Zones and FVGs
    demand_zones = [] # dict: {start_idx: int, end_idx: int, low: float, high: float, active: bool, confirmed_by_bos: bool}
    supply_zones = [] # dict: {start_idx: int, end_idx: int, low: float, high: float, active: bool, confirmed_by_bos: bool}
    fvgs = []         # dict: {type: 'bullish'/'bearish', start_idx: int, low: float, high: float, active: bool}
    liquidity_grabs = [] # dict: {idx: int, type: 'buy'/'sell', level: float, wick_size: float}
    
    trends_series = []

    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    opens = df['open'].values
    times = df['timestamp'].values if 'timestamp' in df.columns else df.index.values

    for i in range(len(df)):
        # Update swing point records
        if df.iloc[i]['is_swing_high']:
            val = highs[i]
            label = ""
            if last_sh_val is not np.nan:
                label = "HH" if val > last_sh_val else "LH"
            else:
                label = "SH"
            last_sh_idx = i
            last_sh_val = val
            swing_highs.append({'idx': i, 'val': val, 'time': times[i]})
            swings_history.append({'type': 'SH', 'idx': i, 'price': val, 'label': label})
            
        if df.iloc[i]['is_swing_low']:
            val = lows[i]
            label = ""
            if last_sl_val is not np.nan:
                label = "HL" if val > last_sl_val else "LL"
            else:
                label = "SL"
            last_sl_idx = i
            last_sl_val = val
            swing_lows.append({'idx': i, 'val': val, 'time': times[i]})
            swings_history.append({'type': 'SL', 'idx': i, 'price': val, 'label': label})

        # Classify Trend based on last swings
        sh_swings = [s for s in swings_history if s['type'] == 'SH']
        sl_swings = [s for s in swings_history if s['type'] == 'SL']
        
        if len(sh_swings) >= 2 and len(sl_swings) >= 2:
            last_two_sh = sh_swings[-2:]
            last_two_sl = sl_swings[-2:]
            
            # Uptrend: Higher High & Higher Low
            if last_two_sh[1]['price'] > last_two_sh[0]['price'] and last_two_sl[1]['price'] > last_two_sl[0]['price']:
                trend = "uptrend"
            # Downtrend: Lower Low & Lower High
            elif last_two_sh[1]['price'] < last_two_sh[0]['price'] and last_two_sl[1]['price'] < last_two_sl[0]['price']:
                trend = "downtrend"

        # Detect BOS & CHoCH
        # Bullish BOS: Close above previous swing high in an uptrend
        # Bearish BOS: Close below previous swing low in a downtrend
        # Bullish CHoCH: In a downtrend, close above prior Lower High (LH)
        # Bearish CHoCH: In an uptrend, close below prior Higher Low (HL)
        
        # We need the prior LH and HL to check for CHoCH
        prior_lh = np.nan
        prior_lh_idx = -1
        prior_hl = np.nan
        prior_hl_idx = -1
        
        # Get prior swing structures
        for s in reversed(swings_history[:-1]): # exclude the one that might have just formed
            if s['type'] == 'SH' and s['label'] == 'LH' and np.isnan(prior_lh):
                prior_lh = s['price']
                prior_lh_idx = s['idx']
            if s['type'] == 'SL' and s['label'] == 'HL' and np.isnan(prior_hl):
                prior_hl = s['price']
                prior_hl_idx = s['idx']
            if not np.isnan(prior_lh) and not np.isnan(prior_hl):
                break

        # Check BOS
        if trend == "uptrend" and last_sh_idx != -1 and i > last_sh_idx:
            if closes[i] > last_sh_val:
                bos_list.append({
                    'idx': i,
                    'time': times[i],
                    'type': 'bullish',
                    'level': last_sh_val,
                    'broken_sh_idx': last_sh_idx
                })
                # Trigger Demand Zone creation from origin of this break
                create_supply_demand_zone(df, i, last_sh_idx, 'demand', demand_zones, X_impulse)
                # Reset last_sh_val so we don't break it again until a new swing high forms
                last_sh_val = np.nan 

        elif trend == "downtrend" and last_sl_idx != -1 and i > last_sl_idx:
            if closes[i] < last_sl_val:
                bos_list.append({
                    'idx': i,
                    'time': times[i],
                    'type': 'bearish',
                    'level': last_sl_val,
                    'broken_sl_idx': last_sl_idx
                })
                # Trigger Supply Zone creation from origin of this break
                create_supply_demand_zone(df, i, last_sl_idx, 'supply', supply_zones, X_impulse)
                last_sl_val = np.nan

        # Check CHoCH
        if trend == "downtrend" and not np.isnan(prior_lh) and i > prior_lh_idx:
            if closes[i] > prior_lh:
                choch_list.append({
                    'idx': i,
                    'time': times[i],
                    'type': 'bullish',
                    'level': prior_lh,
                    'broken_lh_idx': prior_lh_idx
                })
                trend = "uptrend"
                create_supply_demand_zone(df, i, prior_lh_idx, 'demand', demand_zones, X_impulse)

        elif trend == "uptrend" and not np.isnan(prior_hl) and i > prior_hl_idx:
            if closes[i] < prior_hl:
                choch_list.append({
                    'idx': i,
                    'time': times[i],
                    'type': 'bearish',
                    'level': prior_hl,
                    'broken_hl_idx': prior_hl_idx
                })
                trend = "downtrend"
                create_supply_demand_zone(df, i, prior_hl_idx, 'supply', supply_zones, X_impulse)

        trends_series.append(trend)

        # Detect FVGs
        # Bullish FVG: Low of candle C > High of candle A
        if i >= 2:
            if lows[i] > highs[i-2] and (closes[i-1] - opens[i-1]) > 0: # Bullish body
                fvgs.append({
                    'type': 'bullish',
                    'start_idx': i-2,
                    'low': highs[i-2],
                    'high': lows[i],
                    'time': times[i-1],
                    'active': True
                })
            # Bearish FVG: High of candle C < Low of candle A
            elif highs[i] < lows[i-2] and (closes[i-1] - opens[i-1]) < 0: # Bearish body
                fvgs.append({
                    'type': 'bearish',
                    'start_idx': i-2,
                    'low': highs[i],
                    'high': lows[i-2],
                    'time': times[i-1],
                    'active': True
                })

        # Detect Liquidity Grab / Sweep
        # Check against equal highs / equal lows or major swing points
        # For simplicity, we check if price wicks beyond the recent swing high/low and then closes back inside.
        if i > 2:
            # Check swing high sweeps
            # Look at previous swing highs that are not too far back (e.g. within last 30 candles)
            recent_sh = [s for s in swing_highs if s['idx'] < i and i - s['idx'] < 30]
            if recent_sh:
                # Find equal highs or just the highest of recent swing highs
                target_level = max(r['val'] for r in recent_sh)
                # If wick goes above target_level, but close is below it
                if highs[i] > target_level and closes[i] < target_level:
                    high_wick = highs[i] - max(opens[i], closes[i])
                    avg_wick = df.iloc[i]['avg_high_wick']
                    if not np.isnan(avg_wick) and high_wick > 1.2 * avg_wick:
                        liquidity_grabs.append({
                            'idx': i,
                            'time': times[i],
                            'type': 'bearish_sweep', # Bearish sweep = sweep of buy-side liquidity
                            'level': target_level,
                            'wick_high': highs[i],
                            'close': closes[i]
                        })

            # Check swing low sweeps
            recent_sl = [s for s in swing_lows if s['idx'] < i and i - s['idx'] < 30]
            if recent_sl:
                target_level = min(r['val'] for r in recent_sl)
                # If wick goes below target_level, but close is above it
                if lows[i] < target_level and closes[i] > target_level:
                    low_wick = min(opens[i], closes[i]) - lows[i]
                    avg_wick = df.iloc[i]['avg_low_wick']
                    if not np.isnan(avg_wick) and low_wick > 1.2 * avg_wick:
                        liquidity_grabs.append({
                            'idx': i,
                            'time': times[i],
                            'type': 'bullish_sweep', # Bullish sweep = sweep of sell-side liquidity
                            'level': target_level,
                            'wick_low': lows[i],
                            'close': closes[i]
                        })

        # Zone Mitigation updates
        # A Demand zone is mitigated if price closes below it.
        # A Supply zone is mitigated if price closes above it.
        for zone in demand_zones:
            if zone['active'] and i > zone['start_idx']:
                if closes[i] < zone['low']:
                    zone['active'] = False
                    zone['mitigation_idx'] = i
                    zone['mitigation_time'] = times[i]

        for zone in supply_zones:
            if zone['active'] and i > zone['start_idx']:
                if closes[i] > zone['high']:
                    zone['active'] = False
                    zone['mitigation_idx'] = i
                    zone['mitigation_time'] = times[i]

        # FVG Mitigation updates
        # Bullish FVG: price goes below its low
        # Bearish FVG: price goes above its high
        for fvg in fvgs:
            if fvg['active'] and i > fvg['start_idx'] + 2:
                if fvg['type'] == 'bullish' and lows[i] < fvg['low']:
                    fvg['active'] = False
                    fvg['mitigation_idx'] = i
                elif fvg['type'] == 'bearish' and highs[i] > fvg['high']:
                    fvg['active'] = False
                    fvg['mitigation_idx'] = i

    df['trend'] = trends_series

    return {
        'df': df,
        'swing_highs': swing_highs,
        'swing_lows': swing_lows,
        'bos': bos_list,
        'choch': choch_list,
        'demand_zones': demand_zones,
        'supply_zones': supply_zones,
        'fvgs': fvgs,
        'liquidity_grabs': liquidity_grabs
    }

def create_supply_demand_zone(df: pd.DataFrame, current_idx: int, break_idx: int, zone_type: str, zones_list: List[Dict], X_impulse: float):
    """
    Creates a supply or demand zone from the origin candle of the break.
    We look backwards from break_idx to find the origin candle.
    The origin candle is the last opposite or range-bound candle before the impulsive breakout.
    """
    highs = df['high'].values
    lows = df['low'].values
    opens = df['open'].values
    closes = df['close'].values
    times = df['timestamp'].values if 'timestamp' in df.columns else df.index.values

    # Step 1: Find the impulse candidate. An impulse candle range >= X * rolling avg range.
    # Let's search back from break_idx up to 10 candles.
    impulse_idx = -1
    for k in range(break_idx, max(0, break_idx - 10), -1):
        c_range = highs[k] - lows[k]
        avg_r = df.iloc[k]['avg_range']
        if not np.isnan(avg_r) and c_range >= X_impulse * avg_r:
            # Confirm direction matches the zone type
            if zone_type == 'demand' and closes[k] > opens[k]:
                impulse_idx = k
                break
            elif zone_type == 'supply' and closes[k] < opens[k]:
                impulse_idx = k
                break

    # If no clear impulse is marked, use the break_idx itself as the start of the move.
    if impulse_idx == -1:
        impulse_idx = break_idx

    # Step 2: Find the origin candle.
    # Look back from impulse_idx to find the last opposite-colored or small candle.
    origin_idx = max(0, impulse_idx - 1)
    for k in range(impulse_idx - 1, max(0, impulse_idx - 6), -1):
        if zone_type == 'demand':
            # Look for the last bearish or small candle
            if closes[k] < opens[k] or abs(closes[k] - opens[k]) < (highs[k] - lows[k]) * 0.3:
                origin_idx = k
                break
        else: # supply
            # Look for the last bullish or small candle
            if closes[k] > opens[k] or abs(closes[k] - opens[k]) < (highs[k] - lows[k]) * 0.3:
                origin_idx = k
                break

    # Step 3: Define zone coordinates and append.
    zones_list.append({
        'start_idx': origin_idx,
        'time': times[origin_idx],
        'low': lows[origin_idx],
        'high': highs[origin_idx],
        'active': True,
        'confirmed_by_idx': current_idx,
        'confirmed_by_time': times[current_idx]
    })
