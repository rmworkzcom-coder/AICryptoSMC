import os
import json
import logging
import asyncio
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import pandas as pd
import requests

from backend.live_trader import LiveTrader, log_file
from backend.backtester import run_backtest
from backend.smc_engine import calculate_smc
import numpy as np

def serialize_numpy(obj):
    if isinstance(obj, dict):
        return {k: serialize_numpy(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_numpy(i) for i in obj]
    elif isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return serialize_numpy(obj.tolist())
    return obj

app = FastAPI(title="AICryptoSMC API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared LiveTrader instance
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
trader = LiveTrader(config_path)

# Active WebSocket connections
connected_websockets: List[WebSocket] = []

async def broadcast_to_websockets(msg: Dict):
    disconnected = []
    for ws in connected_websockets:
        try:
            await ws.send_json(msg)
        except Exception:
            disconnected.append(ws)
            
    for ws in disconnected:
        if ws in connected_websockets:
            connected_websockets.remove(ws)

# Wire live trader to broadcast messages through websockets
trader.websocket_broadcast_callback = broadcast_to_websockets

class ConfigUpdate(BaseModel):
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None
    testnet: Optional[bool] = None
    trading_mode: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    risk_pct: Optional[float] = None
    rr_ratio: Optional[float] = None
    n_swing: Optional[int] = None
    x_impulse: Optional[float] = None
    m_range: Optional[int] = None
    breakeven_trigger: Optional[float] = None
    max_active_trades: Optional[int] = None
    selected_symbol: Optional[str] = None
    symbols: Optional[List[str]] = None

class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str
    initial_balance: float = 10000.0
    risk_pct: float = 1.0
    rr_ratio: float = 2.0
    n_swing: int = 2
    x_impulse: float = 2.0
    m_range: int = 5
    breakeven_trigger: float = 1.0
    limit: int = 500

@app.get("/config")
def get_config():
    return trader.load_config()

@app.post("/config")
def update_config(cfg: ConfigUpdate):
    updates = {k: v for k, v in cfg.model_dump().items() if v is not None}
    trader.update_config(updates)
    return trader.config

@app.post("/bot/start")
async def start_bot():
    if trader.running:
        return {"status": "already running"}
    await trader.start()
    return {"status": "started"}

@app.post("/bot/stop")
async def stop_bot():
    if not trader.running:
        return {"status": "already stopped"}
    await trader.stop()
    return {"status": "stopped"}

@app.get("/bot/status")
def get_status():
    selected_symbol = trader.config.get("selected_symbol", trader.config.get("symbol", "BTCUSDT"))
    latest_close = 0.0
    latest_trend = "neutral"
    
    df = trader.dfs.get(selected_symbol)
    if df is not None and len(df) > 0:
        latest_close = float(df.iloc[-1]['close'])
        latest_trend = df.iloc[-1]['trend']
    elif trader.df is not None and len(trader.df) > 0:
        latest_close = float(trader.df.iloc[-1]['close'])
        latest_trend = trader.df.iloc[-1]['trend']
        
    scanned_symbols_status = {}
    for symbol, df_sym in trader.dfs.items():
        if len(df_sym) > 0:
            latest_candle = df_sym.iloc[-1]
            scanned_symbols_status[symbol] = {
                "price": float(latest_candle['close']),
                "trend": latest_candle['trend'],
                "has_active_trade": symbol in trader.active_trades,
                "is_swing_high": bool(latest_candle['is_swing_high']),
                "is_swing_low": bool(latest_candle['is_swing_low'])
            }
        
    return {
        "running": trader.running,
        "symbol": selected_symbol,
        "selected_symbol": selected_symbol,
        "timeframe": trader.config.get("timeframe"),
        "paper_balance": trader.paper_balance,
        "active_trades": trader.active_trades,
        "active_trade": trader.active_trade,  # legacy support
        "latest_price": latest_close,
        "latest_trend": latest_trend,
        "scanned_symbols_status": scanned_symbols_status
    }

@app.get("/trades")
async def get_trades():
    return {
        "active_trades": trader.active_trades,
        "active_trade": trader.active_trade,  # legacy support
        "trade_history": trader.trade_history,
        "paper_balance": trader.paper_balance
    }

@app.post("/trades/reset")
async def reset_trades():
    trader.reset_trades()
    return {
        "status": "success",
        "active_trades": trader.active_trades,
        "trade_history": trader.trade_history,
        "paper_balance": trader.paper_balance
    }

@app.get("/chart")
def get_chart(symbol: Optional[str] = None):
    target_symbol = symbol or trader.config.get("selected_symbol", trader.config.get("symbol", "BTCUSDT"))
    
    df = trader.dfs.get(target_symbol)
    if df is None or len(df) == 0:
        if trader.df is not None and len(trader.df) > 0 and trader.config.get("symbol") == target_symbol:
            df = trader.df
        else:
            return {"chart_data": [], "structures": {}}
    
    # Calculate SMC indicators on current df
    smc_res = calculate_smc(
        df,
        N=trader.config.get("n_swing", 2),
        X_impulse=trader.config.get("x_impulse", 2.0),
        M_range=trader.config.get("m_range", 5)
    )
    
    # Only keep essential columns to reduce size
    calc_df = smc_res['df']
    clean_df_cols = ['open', 'high', 'low', 'close']
    if 'timestamp' in calc_df.columns:
        clean_df_cols.append('timestamp')
    chart_df = calc_df[clean_df_cols].copy()
    if 'timestamp' not in chart_df.columns:
        chart_df['timestamp'] = chart_df.index
        
    chart_data = chart_df.to_dict(orient='records')
    
    return serialize_numpy({
        "chart_data": chart_data,
        "structures": {
            "bos": smc_res["bos"],
            "choch": smc_res["choch"],
            "sweeps": smc_res["liquidity_grabs"],
            "swing_highs": smc_res["swing_highs"],
            "swing_lows": smc_res["swing_lows"],
        }
    })


@app.post("/backtest")
def execute_backtest(req: BacktestRequest):
    # Fetch data
    symbol = req.symbol
    timeframe = req.timeframe
    limit = req.limit

    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Binance fetch failed: {response.text}")
        
        klines = response.json()
        data = []
        for k in klines:
            data.append({
                'timestamp': int(k[0]),
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5])
            })
        df = pd.DataFrame(data)
        
        # Run Backtest
        results = run_backtest(
            df,
            initial_balance=req.initial_balance,
            risk_pct=req.risk_pct,
            rr_ratio=req.rr_ratio,
            N_swing=req.n_swing,
            X_impulse=req.x_impulse,
            M_range=req.m_range,
            breakeven_trigger=req.breakeven_trigger
        )
        return serialize_numpy(results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest error: {str(e)}")

@app.get("/logs")
def get_logs(lines: int = 100):
    if not os.path.exists(log_file):
        return []
    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()
            # Return last N lines formatted
            logs = []
            for line in all_lines[-lines:]:
                parts = line.strip().split(" - ", 2)
                if len(parts) == 3:
                    logs.append({
                        "time": parts[0],
                        "level": parts[1],
                        "message": parts[2]
                    })
                else:
                    logs.append({
                        "time": "",
                        "level": "INFO",
                        "message": line.strip()
                    })
            return logs
    except Exception as e:
        return [{"time": "", "level": "ERROR", "message": f"Failed to read logs: {e}"}]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    # Send initial status
    try:
        selected_symbol = trader.config.get("selected_symbol", trader.config.get("symbol", "BTCUSDT"))
        latest_close = 0.0
        latest_trend = "neutral"
        
        df = trader.dfs.get(selected_symbol)
        if df is not None and len(df) > 0:
            latest_close = float(df.iloc[-1]['close'])
            latest_trend = df.iloc[-1].get('trend', 'neutral')
        elif trader.df is not None and len(trader.df) > 0:
            latest_close = float(trader.df.iloc[-1]['close'])
            latest_trend = trader.df.iloc[-1].get('trend', 'neutral')
            
        scanned_symbols_status = {}
        for symbol, df_sym in trader.dfs.items():
            if len(df_sym) > 0:
                latest_candle = df_sym.iloc[-1]
                scanned_symbols_status[symbol] = {
                    "price": float(latest_candle['close']),
                    "trend": latest_candle.get('trend', 'neutral'),
                    "has_active_trade": symbol in trader.active_trades,
                    "is_swing_high": bool(latest_candle.get('is_swing_high', False)),
                    "is_swing_low": bool(latest_candle.get('is_swing_low', False))
                }
                
        await websocket.send_json({
            "type": "state",
            "data": {
                "running": trader.running,
                "symbol": selected_symbol,
                "selected_symbol": selected_symbol,
                "timeframe": trader.config.get("timeframe"),
                "active_trades": trader.active_trades,
                "active_trade": trader.active_trade,  # legacy support
                "balance": trader.paper_balance,
                "latest_price": latest_close,
                "latest_trend": latest_trend,
                "scanned_symbols_status": scanned_symbols_status,
                "trade_history": trader.trade_history
            }
        })
        
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)
    except Exception:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)

@app.on_event("startup")
async def startup_event():
    # If bot was previously running in config, start it automatically on reboot
    config = trader.load_config()
    if config.get("running", False):
        await trader.start()

@app.on_event("shutdown")
async def shutdown_event():
    await trader.stop(is_shutdown=True)
