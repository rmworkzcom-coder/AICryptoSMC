import pandas as pd
import numpy as np
from typing import Dict, List, Any
from backend.smc_engine import calculate_smc

def run_backtest(df: pd.DataFrame, 
                 initial_balance: float = 1600.0,
                 risk_pct: float = 1.0, # 1% risk per trade
                 rr_ratio: float = 2.0,  # 2:1 Risk to Reward
                 N_swing: int = 2,
                 X_impulse: float = 2.0,
                 M_range: int = 5,
                 breakeven_trigger: float = 1.0) -> Dict[str, Any]:
    """
    Runs an SMC trading strategy backtest over historical data.
    """
    # Calculate SMC indicators
    smc_res = calculate_smc(df, N=N_swing, X_impulse=X_impulse, M_range=M_range)
    
    # Extract calculated data
    calc_df = smc_res['df']
    swing_highs = smc_res['swing_highs']
    swing_lows = smc_res['swing_lows']
    bos_events = smc_res['bos']
    choch_events = smc_res['choch']
    demand_zones = smc_res['demand_zones']
    supply_zones = smc_res['supply_zones']
    fvgs = smc_res['fvgs']
    sweeps = smc_res['liquidity_grabs']

    # Convert events into fast-lookup structures
    # Sweeps by index
    sweeps_by_idx = {sw['idx']: sw for sw in sweeps}
    
    # System states
    balance = initial_balance
    active_trade = None # Dict
    trade_history = []
    equity_curve = []
    
    highs = calc_df['high'].values
    lows = calc_df['low'].values
    closes = calc_df['close'].values
    opens = calc_df['open'].values
    times = calc_df['timestamp'].values if 'timestamp' in calc_df.columns else calc_df.index.values
    trends = calc_df['trend'].values

    for i in range(len(calc_df)):
        equity_curve.append({
            'time': int(times[i]),
            'balance': balance
        })
        
        # 1. Manage Active Trade
        if active_trade is not None:
            trade_type = active_trade['type']
            entry_price = active_trade['entry_price']
            sl = active_trade['sl']
            tp = active_trade['tp']
            size = active_trade['size']
            risk_amount = active_trade['risk_amount']
            breakeven_set = active_trade.get('breakeven_set', False)

            # Check breakeven trigger
            if not breakeven_set and breakeven_trigger > 0:
                if trade_type == 'long':
                    # If price moved up by 1.0R (breakeven_trigger * risk_amount)
                    if highs[i] >= entry_price + (breakeven_trigger * (entry_price - sl)):
                        active_trade['sl'] = entry_price
                        active_trade['breakeven_set'] = True
                elif trade_type == 'short':
                    # If price moved down by 1.0R
                    if lows[i] <= entry_price - (breakeven_trigger * (sl - entry_price)):
                        active_trade['sl'] = entry_price
                        active_trade['breakeven_set'] = True

            # Re-read SL/TP in case breakeven was set
            sl = active_trade['sl']

            if trade_type == 'long':
                # Check if SL is hit
                if lows[i] <= sl:
                    # Executed SL
                    exit_price = sl
                    pnl = (exit_price - entry_price) * size
                    balance += pnl
                    trade_history.append({
                        **active_trade,
                        'exit_idx': i,
                        'exit_time': int(times[i]),
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'status': 'SL' if pnl < 0 else 'BE'
                    })
                    active_trade = None
                # Check if TP is hit
                elif highs[i] >= tp:
                    exit_price = tp
                    pnl = (exit_price - entry_price) * size
                    balance += pnl
                    trade_history.append({
                        **active_trade,
                        'exit_idx': i,
                        'exit_time': int(times[i]),
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'status': 'TP'
                    })
                    active_trade = None
            elif trade_type == 'short':
                # Check if SL is hit
                if highs[i] >= sl:
                    exit_price = sl
                    pnl = (entry_price - exit_price) * size
                    balance += pnl
                    trade_history.append({
                        **active_trade,
                        'exit_idx': i,
                        'exit_time': int(times[i]),
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'status': 'SL' if pnl < 0 else 'BE'
                    })
                    active_trade = None
                # Check if TP is hit
                elif lows[i] <= tp:
                    exit_price = tp
                    pnl = (entry_price - exit_price) * size
                    balance += pnl
                    trade_history.append({
                        **active_trade,
                        'exit_idx': i,
                        'exit_time': int(times[i]),
                        'exit_price': exit_price,
                        'pnl': pnl,
                        'status': 'TP'
                    })
                    active_trade = None

        # 2. Check for entry setups if no active trade
        if active_trade is None:
            # Current trend
            current_trend = trends[i]
            
            # Check if there is a sweep at the current index
            sweep = sweeps_by_idx.get(i)
            
            if sweep is not None:
                sweep_type = sweep['type']
                
                # Setup Long: Trend is uptrend, and we have a bullish sweep (sell-side liquidity swept)
                if current_trend == 'uptrend' and sweep_type == 'bullish_sweep':
                    # Find an active demand zone or bullish FVG that this sweep penetrated
                    sweep_low = sweep['wick_low']
                    matching_zone = None
                    
                    # Search for active demand zones
                    for zone in demand_zones:
                        is_active_at_i = zone.get('active', True) or zone.get('mitigation_idx', len(calc_df)) > i
                        if is_active_at_i and zone['start_idx'] < i:
                            # Sweep wick low goes into/below demand zone high, but close is above demand zone low
                            if sweep_low <= zone['high'] and closes[i] >= zone['low']:
                                matching_zone = zone
                                break
                    
                    # If we found a matching zone, execute long
                    if matching_zone:
                        entry_price = closes[i]
                        # Stop loss is below the sweep low
                        stop_loss = sweep_low - (entry_price * 0.0005) # 0.05% buffer
                        risk_per_share = entry_price - stop_loss
                        
                        if risk_per_share > 0:
                            risk_usd = balance * (risk_pct / 100.0)
                            size = risk_usd / risk_per_share
                            take_profit = entry_price + (rr_ratio * risk_per_share)
                            
                            active_trade = {
                                'type': 'long',
                                'entry_idx': i,
                                'entry_time': int(times[i]),
                                'entry_price': entry_price,
                                'sl': stop_loss,
                                'tp': take_profit,
                                'size': size,
                                'risk_amount': risk_usd,
                                'zone_start_idx': matching_zone['start_idx']
                            }
                
                # Setup Short: Trend is downtrend, and we have a bearish sweep (buy-side liquidity swept)
                elif current_trend == 'downtrend' and sweep_type == 'bearish_sweep':
                    # Find an active supply zone or bearish FVG that this sweep penetrated
                    sweep_high = sweep['wick_high']
                    matching_zone = None
                    
                    # Search for active supply zones
                    for zone in supply_zones:
                        is_active_at_i = zone.get('active', True) or zone.get('mitigation_idx', len(calc_df)) > i
                        if is_active_at_i and zone['start_idx'] < i:
                            # Sweep wick high goes into/above supply zone low, but close is below supply zone high
                            if sweep_high >= zone['low'] and closes[i] <= zone['high']:
                                matching_zone = zone
                                break
                                
                    if matching_zone:
                        entry_price = closes[i]
                        # Stop loss is above the sweep high
                        stop_loss = sweep_high + (entry_price * 0.0005) # 0.05% buffer
                        risk_per_share = stop_loss - entry_price
                        
                        if risk_per_share > 0:
                            risk_usd = balance * (risk_pct / 100.0)
                            size = risk_usd / risk_per_share
                            take_profit = entry_price - (rr_ratio * risk_per_share)
                            
                            active_trade = {
                                'type': 'short',
                                'entry_idx': i,
                                'entry_time': int(times[i]),
                                'entry_price': entry_price,
                                'sl': stop_loss,
                                'tp': take_profit,
                                'size': size,
                                'risk_amount': risk_usd,
                                'zone_start_idx': matching_zone['start_idx']
                            }

    # Summary Stats
    total_trades = len(trade_history)
    wins = [t for t in trade_history if t['status'] == 'TP']
    losses = [t for t in trade_history if t['status'] == 'SL']
    breakevens = [t for t in trade_history if t['status'] == 'BE']
    
    win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
    net_profit = balance - initial_balance
    return_pct = (net_profit / initial_balance) * 100.0
    
    total_win_amount = sum(t['pnl'] for t in wins)
    total_loss_amount = abs(sum(t['pnl'] for t in losses))
    profit_factor = (total_win_amount / total_loss_amount) if total_loss_amount > 0 else (total_win_amount if total_win_amount > 0 else 1.0)

    # Clean DataFrame for JSON response
    # Only keep essential columns to reduce size
    clean_df_cols = ['open', 'high', 'low', 'close', 'trend']
    if 'timestamp' in calc_df.columns:
        clean_df_cols.append('timestamp')
    chart_df = calc_df[clean_df_cols].copy()
    if 'timestamp' not in chart_df.columns:
        chart_df['timestamp'] = chart_df.index
        
    chart_data = chart_df.to_dict(orient='records')

    return {
        'summary': {
            'initial_balance': initial_balance,
            'final_balance': balance,
            'net_profit': net_profit,
            'return_pct': return_pct,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'wins_count': len(wins),
            'losses_count': len(losses),
            'be_count': len(breakevens)
        },
        'trades': trade_history,
        'equity_curve': equity_curve,
        'chart_data': chart_data,
        'structures': {
            'swing_highs': swing_highs,
            'swing_lows': swing_lows,
            'bos': bos_events,
            'choch': choch_events,
            'demand_zones': [z for z in demand_zones if not z['active']], # resolved
            'active_demand_zones': [z for z in demand_zones if z['active']],
            'supply_zones': [z for z in supply_zones if not z['active']],
            'active_supply_zones': [z for z in supply_zones if z['active']],
            'fvgs': fvgs,
            'sweeps': sweeps
        }
    }
