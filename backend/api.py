import os
import json
import logging
import asyncio
import time
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import pandas as pd
import requests

from backend.live_trader import LiveTrader, log_file
from backend.backtester import run_backtest
from backend.smc_engine import calculate_smc
from backend.constants import DEFAULT_INITIAL_BALANCE
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
trader.log_message(f"Backend startup: trading_mode={trader.config.get('trading_mode')} portfolio_margin={trader.config.get('portfolio_margin')} testnet={trader.config.get('testnet')}")

# Active WebSocket connections
connected_websockets: List[WebSocket] = []

async def broadcast_to_websockets(msg: Dict):
    to_remove = []
    send_tasks = []
    logging.info(f"Broadcast requested: msg_type={msg.get('type')} current_connected={len(connected_websockets)}")

    async def _send(ws: WebSocket):
        try:
            # Ensure message is JSON serializable
            encoded = jsonable_encoder(msg)
            client_info = getattr(ws, 'client', None)
            logging.debug(f"Sending websocket message to client={client_info} msg_type={msg.get('type')}")
            await asyncio.wait_for(ws.send_json(encoded), timeout=5)
            logging.debug(f"Successfully sent websocket message to client={client_info}")
        except Exception as e:
            # Log detailed info for debugging intermittent websocket failures
            client_info = getattr(ws, 'client', None)
            try:
                logging.warning(f"WebSocket send failed to client={client_info}: {e}")
            except Exception:
                logging.warning("WebSocket send failed (error while logging client info)")
            to_remove.append(ws)

    for ws in list(connected_websockets):
        send_tasks.append(asyncio.create_task(_send(ws)))

    if send_tasks:
        # wait for all sends to complete, but don't fail the caller if one fails
        await asyncio.gather(*send_tasks, return_exceptions=True)

    for ws in to_remove:
        if ws in connected_websockets:
            try:
                await ws.close()
            except Exception:
                pass
            connected_websockets.remove(ws)
    logging.info(f"Broadcast complete: attempted={len(send_tasks)} remaining_connected={len(connected_websockets)}")


@app.post("/_internal/ws/test-broadcast")
async def _internal_test_broadcast():
    """Internal endpoint used to test websocket broadcasts from the running server.
    Sends a short test message to all currently connected websockets and returns counts.
    """
    # Snapshot current clients
    attempted = len(list(connected_websockets))
    test_msg = {
        "type": "test",
        "data": {"message": "internal test broadcast", "ts": int(time.time() * 1000)}
    }
    await broadcast_to_websockets(test_msg)
    remaining = len(connected_websockets)
    return {"status": "ok", "attempted": attempted, "remaining": remaining}

# Wire live trader to broadcast messages through websockets
trader.websocket_broadcast_callback = broadcast_to_websockets

def build_state_payload() -> Dict:
    trader.config = trader.load_config()
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
    
    total_symbols = trader.scan_total or len(trader.config.get("symbols", []))
    scanned_count = trader.scan_progress if trader.scan_progress > 0 else len(scanned_symbols_status)
    skipped_count = trader.skipped_symbols if trader.scan_progress > 0 else (max(0, total_symbols - len(scanned_symbols_status)) if scanned_symbols_status else 0)

    active_trades = trader.active_trades
    balance = trader.paper_balance

    # Normalize binance auth status for UI: avoid showing 'pending' when it's stale
    auth_status = trader.binance_auth_status
    try:
        trading_mode = trader.config.get("trading_mode")
    except Exception:
        trading_mode = None
    if auth_status == "pending":
        if trading_mode != "live":
            auth_status = "unknown"
        elif getattr(trader, 'client', None) is None:
            auth_status = "failed"

    return {
        "scanning": getattr(trader, 'scanning', False),
        "running": trader.running,
        "symbol": selected_symbol,
        "selected_symbol": selected_symbol,
        "timeframe": trader.config.get("timeframe"),
        "active_trades": active_trades,
        "active_trade": trader.active_trade,
        "balance": balance,
        "paper_balance": balance,
        "initial_balance": DEFAULT_INITIAL_BALANCE,
        "latest_price": latest_close,
        "latest_trend": latest_trend,
        "scanned_symbols_status": scanned_symbols_status,
        "scan_total": total_symbols,
        "scan_count": scanned_count,
        "scan_skipped": skipped_count,
        "signals_found": trader.signals_found,
        "open_trades_created": trader.open_trades_created,
        "skipped_symbols": trader.skipped_symbols,
        "scan_cycle_count": trader.scan_cycle_count,
        "trading_mode": trader.config.get("trading_mode", "paper"),
        "portfolio_margin": trader.config.get("portfolio_margin", False),
        "binance_auth_status": auth_status,
        "binance_auth_source": trader.binance_auth_source,
        "binance_auth_message": trader.binance_auth_message,
        "binance_auth_mode": trader.binance_auth_mode,
        # If the live status is not success but we have a recent successful auth,
        # expose that to the UI so transient failures don't immediately flip the dashboard.
        "binance_last_success": getattr(trader, '_last_successful_auth', (None, None, None, 0.0)),
        "scan_interval_secs": trader.config.get("scan_interval_secs", 15),
        "scan_last_broadcast_at": getattr(trader, 'scan_last_broadcast_at', int(time.time() * 1000)),
        "trade_history": trader.trade_history
    }

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
    peak_drawdown_exit_pct: Optional[float] = None
    peak_profit_retrace_pct: Optional[float] = None
    peak_profit_retrace_min_usd: Optional[float] = None
    max_trade_loss_pct: Optional[float] = None
    max_trade_loss_usd: Optional[float] = None
    max_active_trades: Optional[int] = None
    selected_symbol: Optional[str] = None
    symbols: Optional[List[str]] = None
    portfolio_margin: Optional[bool] = None
    symbol: str
    timeframe: str
    initial_balance: float = DEFAULT_INITIAL_BALANCE
    risk_pct: float = 1.0
    rr_ratio: float = 2.0
    n_swing: int = 2
    x_impulse: float = 2.0
    m_range: int = 5
    breakeven_trigger: float = 1.0
    limit: int = 500


class BacktestRequest(BaseModel):
    symbol: str
    timeframe: str
    initial_balance: float = DEFAULT_INITIAL_BALANCE
    risk_pct: float = 1.0
    rr_ratio: float = 2.0
    n_swing: int = 2
    x_impulse: float = 2.0
    m_range: int = 5
    breakeven_trigger: float = 1.0
    limit: int = 500


class OpenTradeRequest(BaseModel):
    symbol: Optional[str] = None
    trade_type: str  # 'long' or 'short'
    entry_price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    size: Optional[float] = None
    risk_usd: Optional[float] = None


class UnfreezeRequest(BaseModel):
    symbol: str

@app.get("/config")
def get_config():
    return trader.config

@app.post("/config")
def update_config(cfg: ConfigUpdate):
    updates = {k: v for k, v in cfg.model_dump().items() if v is not None}
    trader.update_config(updates)
    return trader.config

@app.post("/bot/start")
async def start_bot():
    if trader.running:
        return {"status": "already running"}
    asyncio.create_task(trader.start())
    return {"status": "starting"}

@app.post("/bot/stop")
async def stop_bot():
    if not trader.running:
        return {"status": "already stopped"}
    await trader.stop()
    return {"status": "stopped"}

@app.get("/bot/status")
def get_status():
    return build_state_payload()


@app.post("/bot/check-auth")
def check_auth():
    """Trigger a lightweight auth check using keys from environment or .env files
    without enabling live trading. Returns current auth status and message.
    """
    try:
        ok = trader.check_env_auth()
        return {
            "success": bool(ok),
            "binance_auth_status": trader.binance_auth_status,
            "binance_auth_message": trader.binance_auth_message,
            "binance_auth_source": trader.binance_auth_source,
            "binance_auth_mode": trader.binance_auth_mode,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trades")
async def get_trades():
    return {
        "active_trades": trader.get_exchange_positions(),
        "active_trade": trader.active_trade,  # legacy support
        "trade_history": trader.trade_history,
        "paper_balance": trader.get_live_balance(),
        "initial_balance": DEFAULT_INITIAL_BALANCE
    }


@app.post("/trades/open")
def open_trade(req: OpenTradeRequest):
    """Open a manual trade. If prices or size are omitted, the server will
    attempt to compute sensible defaults using current price and config.
    """
    try:
        symbol = req.symbol or trader.config.get("selected_symbol", trader.config.get("symbol", "BTCUSDT"))
        trade_type = req.trade_type.lower()
        if trade_type not in ("long", "short"):
            raise HTTPException(status_code=400, detail="trade_type must be 'long' or 'short'")

        entry_price = req.entry_price or trader.get_latest_price(symbol)
        if not entry_price or entry_price <= 0:
            raise HTTPException(status_code=400, detail=f"Unable to determine entry price for {symbol}")

        # If SL/TP missing, attempt to infer from config and default risk sizing
        sl = req.sl
        tp = req.tp
        size = req.size
        risk_usd = req.risk_usd

        if (sl is None or tp is None) and size is None:
            # Try to infer using trader._infer_missing_sl_tp by reverse-engineering risk
            rr = trader.config.get('rr_ratio', 2.0)
            # Use a default risk_per_share (0.5% of entry)
            est_risk_per_share = max(entry_price * 0.005, 1e-8)
            if trade_type == 'long':
                sl = sl or (entry_price - est_risk_per_share)
                tp = tp or (entry_price + rr * est_risk_per_share)
            else:
                sl = sl or (entry_price + est_risk_per_share)
                tp = tp or (entry_price - rr * est_risk_per_share)

        # Size determination: prefer explicit size, then risk_usd, then risk_pct from config
        if size is None:
            if risk_usd is None:
                risk_pct = trader.config.get('risk_pct', 1.0)
                current_balance = trader.get_live_balance()
                risk_usd = current_balance * (risk_pct / 100.0)
            risk_per_share = abs(entry_price - sl) if sl is not None else max(entry_price * 0.005, 1e-8)
            if risk_per_share <= 0:
                raise HTTPException(status_code=400, detail="Computed non-positive risk per share")
            size = risk_usd / risk_per_share

        entry_time = int(time.time() * 1000)
        trader.open_trade(symbol, trade_type, float(entry_price), float(sl), float(tp), float(size), float(risk_usd or 0.0), entry_time, 0)
        return {
            "status": "ok",
            "active_trades": trader.active_trades,
            "trade_history": trader.trade_history,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/trades/reset")
async def reset_trades():
    trader.reset_trades()
    return {
        "status": "success",
        "active_trades": trader.active_trades,
        "trade_history": trader.trade_history,
        "paper_balance": trader.get_live_balance(),
        "initial_balance": DEFAULT_INITIAL_BALANCE
    }


@app.post("/trades/unfreeze")
def unfreeze_trade(req: UnfreezeRequest):
    """Remove a symbol from the frozen_symbols map so it can be re-entered."""
    symbol = req.symbol
    if symbol in trader.frozen_symbols:
        try:
            del trader.frozen_symbols[symbol]
            trader.save_trades()
            return {"status": "success", "message": f"Unfroze {symbol}"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"status": "not_found", "message": f"{symbol} was not frozen"}


@app.post("/trades/backfill")
def backfill_trades():
    """Trigger background backfill of missing order IDs from PAPI for historical trades.
    Returns a brief summary of updated records.
    """
    try:
        if trader.config.get('trading_mode') != 'live' and not trader.config.get('portfolio_margin', False):
            return {"status": "skipped", "message": "Backfill requires live portfolio_margin mode enabled."}
        res = trader.backfill_missing_order_ids()
        return {"status": "ok", "updated": res.get('updated', 0), "scanned": res.get('scanned', 0)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/trades/liquidate")
async def liquidate_trades(symbol: Optional[str] = None):
    if symbol:
        trader.liquidate_trade(symbol)
    else:
        trader.liquidate_all_trades()
    return {
        "status": "success",
        "active_trades": trader.active_trades,
        "trade_history": trader.trade_history,
        "paper_balance": trader.get_live_balance(),
        "initial_balance": DEFAULT_INITIAL_BALANCE
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

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await websocket.accept()
    except Exception as e:
        logging.warning(f"Failed to accept websocket: {e}")
        return
    # Log client and handshake headers for debugging intermittent disconnects
    try:
        client_info = getattr(websocket, 'client', None)
        scope_headers = websocket.scope.get('headers', []) if hasattr(websocket, 'scope') else []
        headers = {k.decode(): v.decode() for k, v in scope_headers}
        logging.info(f"WebSocket /api/ws [accepted] client={client_info} headers={headers}")
    except Exception:
        logging.warning("Error logging websocket handshake details")
    connected_websockets.append(websocket)
    try:
        # Send a minimal initial handshake only. The frontend will fetch full status via HTTP.
        try:
            minimal = {
                "type": "state",
                "data": {
                    "running": bool(getattr(trader, 'running', False)),
                    "scan_total": trader.scan_total or len(trader.config.get("symbols", [])),
                    "binance_auth_status": getattr(trader, 'binance_auth_status', 'unknown'),
                    "binance_auth_message": getattr(trader, 'binance_auth_message', None)
                }
            }
            await asyncio.wait_for(websocket.send_json(minimal), timeout=5)
        except Exception:
            logging.info("Failed to send minimal websocket handshake on connect (ignored)")
            # Continue; do not abort connection. Client will retry status over HTTP if needed.

        # Keep connection alive. Use low-level receive() so we properly handle
        # protocol-level events (text/binary/close) and avoid relying on an
        # application-level "pong" string. Periodically send lightweight
        # app-level pings to prompt clients that expect them.
        PING_INTERVAL = 30

        async def _send_ping():
            await websocket.send_json({"type": "ping", "time": int(time.time() * 1000)})

        while True:
            try:
                # Wait for any websocket event (receive text/binary or disconnect)
                event = await asyncio.wait_for(websocket.receive(), timeout=PING_INTERVAL)
                etype = event.get('type')
                # If a normal text message arrives, ignore it (frontend polls HTTP)
                if etype == 'websocket.receive':
                    # reset timer by continuing; if text exists, optionally inspect
                    # for debug-friendly messages but do not demand a literal 'pong'
                    text = event.get('text')
                    if text:
                        try:
                            # quietly parse JSON if provided and ignore
                            _ = json.loads(text)
                        except Exception:
                            pass
                    continue
                elif etype == 'websocket.disconnect':
                    # client requested close
                    break
                else:
                    # Unknown event types are tolerated; continue loop
                    continue
            except asyncio.TimeoutError:
                # No event within the interval — send an app-level ping and keep-alive
                try:
                    await asyncio.wait_for(_send_ping(), timeout=5)
                except Exception as e:
                    # Don't immediately close the connection on a transient ping send error.
                    # Log the failure and allow the receive loop to detect disconnects.
                    logging.warning(f"WebSocket ping failed ({e}); continuing and awaiting next event")
                    # Small backoff to avoid busy-looping on persistent send failures
                    await asyncio.sleep(1)
                    continue
            except WebSocketDisconnect:
                break
            except Exception as e:
                logging.warning(f"WebSocket error during receive (closing): {e}")
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        logging.warning("WebSocket error")
    finally:
        try:
            if websocket in connected_websockets:
                connected_websockets.remove(websocket)
        except Exception:
            logging.warning("Failed to remove websocket from connected list on cleanup")

@app.on_event("startup")
async def startup_event():
    # If bot was previously running in config, start it automatically on reboot
    config = trader.load_config()
    if config.get("running", False):
        await trader.start()

@app.on_event("shutdown")
async def shutdown_event():
    await trader.stop(is_shutdown=True)
