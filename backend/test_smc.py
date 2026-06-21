import pandas as pd
import numpy as np
from backend.smc_engine import calculate_smc

def create_mock_data() -> pd.DataFrame:
    """
    Creates a dummy dataset with clear swing points to test the indicators.
    """
    # 50 candles
    n = 50
    timestamps = [1700000000 + i * 900 for i in range(n)] # 15m intervals
    
    # Generate simple sine wave for prices to form natural swing highs/lows
    x = np.linspace(0, 4 * np.pi, n)
    base_price = 100.0 + 10.0 * np.sin(x)
    
    opens = base_price - 1.0 + np.random.normal(0, 0.2, n)
    closes = base_price + 1.0 + np.random.normal(0, 0.2, n)
    highs = np.maximum(opens, closes) + 2.0
    lows = np.minimum(opens, closes) - 2.0
    volumes = np.random.randint(100, 1000, n)
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    return df

def test_smc_calculation():
    df = create_mock_data()
    print(f"Generated mock data with {len(df)} candles.")
    
    res = calculate_smc(df, N=2, X_impulse=1.5, M_range=5)
    
    print("\n--- SMC Calculation Results ---")
    print(f"Swing Highs found: {len(res['swing_highs'])}")
    print(f"Swing Lows found: {len(res['swing_lows'])}")
    print(f"BOS events: {len(res['bos'])}")
    print(f"CHoCH events: {len(res['choch'])}")
    print(f"Demand Zones: {len(res['demand_zones'])}")
    print(f"Supply Zones: {len(res['supply_zones'])}")
    print(f"FVG events: {len(res['fvgs'])}")
    print(f"Liquidity Grabs: {len(res['liquidity_grabs'])}")
    
    # Basic assertions
    assert len(df) == 50, "Dataframe length should be 50"
    assert 'trend' in res['df'].columns, "Trend column should be present in results"
    print("\nAll indicators processed successfully!")

if __name__ == "__main__":
    test_smc_calculation()
