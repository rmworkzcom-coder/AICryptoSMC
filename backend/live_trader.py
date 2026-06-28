import asyncio
import json
import logging
import time
import os
import requests
import hmac
import hashlib
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from backend.smc_engine import calculate_smc
from backend.constants import DEFAULT_INITIAL_BALANCE

logger = logging.getLogger("live_trader")
logger.setLevel(logging.INFO)

# Create a local file logger
log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, "trader.log")
file_handler = logging.FileHandler(log_file)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Console output as well
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

class LiveTrader:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self.load_config()
        self.running = False
        self.task = None
        self.client = None
        self.binance_auth_status = "unknown"
        self.binance_auth_source = None
        self.binance_auth_message = None
        self.binance_auth_mode = None
        
        # Multi-symbol trading state
        self.active_trades = {}  # symbol -> trade dict
        self.trade_history = []
        self.paper_balance = DEFAULT_INITIAL_BALANCE
        self.last_candle_times = {}  # symbol -> last_candle_time
        
        # Dataframes cache
        self.df = None  # selected or fallback dataframe (for backwards compatibility)
        self.dfs = {}   # symbol -> dataframe
        self.websocket_broadcast_callback = None
        
        self.trades_file = os.path.join(os.path.dirname(config_path), "trades.json")
        self.load_trades()

    @property
    def active_trade(self) -> Optional[Dict]:
        """Backward compatibility for single-trade lookups (returns first active trade)."""
        if not self.active_trades:
            return None
        return next(iter(self.active_trades.values()))

    @active_trade.setter
    def active_trade(self, value: Optional[Dict]):
        """Backward compatibility setter."""
        if value is None:
            self.active_trades = {}
        else:
            symbol = value.get("symbol", self.config.get("symbol", "BTCUSDT"))
            self.active_trades[symbol] = value

    def load_config(self) -> Dict:
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def save_config(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def load_trades(self):
        self.active_trades = {}
        if os.path.exists(self.trades_file):
            try:
                with open(self.trades_file, 'r') as f:
                    data = json.load(f)
                    self.active_trades = data.get("active_trades", {})
                    # Migration: if active_trade exists and active_trades is empty, migrate it
                    if "active_trade" in data and data["active_trade"] and not self.active_trades:
                        symbol = self.config.get("symbol", "BTCUSDT")
                        self.active_trades[symbol] = data["active_trade"]
                    self.trade_history = data.get("trade_history", [])
                    self.paper_balance = data.get("paper_balance", DEFAULT_INITIAL_BALANCE)
            except Exception as e:
                logger.error(f"Error loading trades.json: {e}")

    def save_trades(self):
        try:
            with open(self.trades_file, 'w') as f:
                json.dump({
                    "active_trades": self.active_trades,
                    "trade_history": self.trade_history,
                    "paper_balance": self.paper_balance
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving trades.json: {e}")

    def reset_trades(self):
        self.active_trades = {}
        self.trade_history = []
        self.paper_balance = DEFAULT_INITIAL_BALANCE
        self.save_trades()
        self.log_message("Trading state and history reset to default.")
        
        # Trigger an immediate state broadcast
        if self.websocket_broadcast_callback:
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(self.broadcast_current_state())
            except RuntimeError:
                pass

    def get_latest_price(self, symbol: str) -> float:
        market_type = self.config.get("market_type", "futures")
        try:
            if market_type == "futures":
                url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}"
            else:
                url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                price = float(data.get('price', 0.0))
                if price > 0:
                    return price
        except Exception as e:
            logger.error(f"Error fetching latest price for {symbol}: {e}")
            
        # Fallback to last candle close if request fails
        df = self.dfs.get(symbol)
        if df is not None and len(df) > 0:
            return float(df.iloc[-1]['close'])
        return 0.0

    def liquidate_trade(self, symbol: str):
        if symbol not in self.active_trades:
            self.log_message(f"No active position for {symbol} to liquidate.")
            return
            
        trading_mode = self.config.get("trading_mode", "paper")
        market_type = self.config.get("market_type", "futures")
        portfolio_margin = self.config.get("portfolio_margin", False)
        
        trade = self.active_trades[symbol]
        trade_type = trade['type']
        entry_price = trade['entry_price']
        size = trade['size']
        
        # Fetch current mark/ticker price for exit_price
        exit_price = self.get_latest_price(symbol)
        if exit_price <= 0:
            exit_price = entry_price
            
        # Calculate PnL
        if trade_type == 'long':
            pnl = (exit_price - entry_price) * size
        else: # short
            pnl = (entry_price - exit_price) * size
            
        # If in live mode, place a market order to close the actual position on the exchange
        if trading_mode == "live":
            opp_side = 'SELL' if trade_type == 'long' else 'BUY'
            self.log_message(f"[{symbol}] Placing Live MARKET Close Order to liquidate position of size {size}...")
            try:
                if market_type == "futures":
                    if portfolio_margin:
                        price_prec, qty_prec = self.get_symbol_precision(symbol, market_type)
                        formatted_qty = round(size, qty_prec)
                        qty_str = f"{formatted_qty:.{max(0, qty_prec)}f}" if qty_prec >= 0 else str(int(formatted_qty))
                        
                        res = self._make_papi_request("POST", "/papi/v1/um/order", {
                            "symbol": symbol,
                            "side": opp_side,
                            "type": "MARKET",
                            "quantity": qty_str
                        })
                        
                        # Use actual execution fill price if available in response
                        if res and isinstance(res, dict):
                            avg_price = res.get('avgPrice')
                            if avg_price and float(avg_price) > 0:
                                exit_price = float(avg_price)
                                if trade_type == 'long':
                                    pnl = (exit_price - entry_price) * size
                                else:
                                    pnl = (entry_price - exit_price) * size
                                self.log_message(f"[{symbol}] Executed Close at avg price {exit_price}")
                    elif self.client:
                        res = self.client.futures_create_order(
                            symbol=symbol,
                            side=opp_side,
                            type=Client.ORDER_TYPE_MARKET,
                            quantity=size
                        )
                        if res and isinstance(res, dict):
                            avg_price = res.get('avgPrice')
                            if avg_price and float(avg_price) > 0:
                                exit_price = float(avg_price)
                                if trade_type == 'long':
                                    pnl = (exit_price - entry_price) * size
                                else:
                                    pnl = (entry_price - exit_price) * size
                elif self.client: # spot
                    self.client.create_order(
                        symbol=symbol,
                        side=Client.SIDE_SELL if trade_type == 'long' else Client.SIDE_BUY,
                        type=Client.ORDER_TYPE_MARKET,
                        quantity=size
                    )
            except Exception as e:
                self.log_message(f"[{symbol}] Failed to execute close order on exchange: {e}", "error")
        
        self.paper_balance += pnl
        self.close_trade(symbol, exit_price, pnl, "LIQ")

    def liquidate_all_trades(self):
        symbols_to_close = list(self.active_trades.keys())
        if not symbols_to_close:
            self.log_message("No active positions to liquidate.")
            return
            
        for symbol in symbols_to_close:
            self.liquidate_trade(symbol)
            
        self.log_message("All active positions have been liquidated.")

    async def broadcast_current_state(self):
        if not self.websocket_broadcast_callback:
            return
        
        selected_symbol = self.config.get("selected_symbol", self.config.get("symbol", "BTCUSDT"))
        timeframe = self.config.get("timeframe", "15m")
        latest_close = 0.0
        latest_trend = "neutral"
        
        df = self.dfs.get(selected_symbol)
        if df is not None and len(df) > 0:
            latest_close = float(df.iloc[-1]['close'])
            latest_trend = df.iloc[-1].get('trend', 'neutral')
        elif self.df is not None and len(self.df) > 0:
            latest_close = float(self.df.iloc[-1]['close'])
            latest_trend = self.df.iloc[-1].get('trend', 'neutral')
            
        scanned_symbols_status = {}
        for symbol, df_sym in self.dfs.items():
            if len(df_sym) > 0:
                latest_candle = df_sym.iloc[-1]
                scanned_symbols_status[symbol] = {
                    "price": float(latest_candle['close']),
                    "trend": latest_candle.get('trend', 'neutral'),
                    "has_active_trade": symbol in self.active_trades,
                    "is_swing_high": bool(latest_candle.get('is_swing_high', False)),
                    "is_swing_low": bool(latest_candle.get('is_swing_low', False))
                }

        total_symbols = len(self.config.get("symbols", []))
        scanned_count = len(scanned_symbols_status)
        skipped_count = max(0, total_symbols - scanned_count)
                
        try:
            live_balance = await asyncio.to_thread(self.get_live_balance)
            await self.websocket_broadcast_callback({
                "type": "state",
                "data": {
                    "running": self.running,
                    "symbol": selected_symbol,
                    "selected_symbol": selected_symbol,
                    "timeframe": timeframe,
                    "active_trades": self.active_trades,
                    "active_trade": self.active_trade,  # legacy support
                    "balance": live_balance,
                    "initial_balance": DEFAULT_INITIAL_BALANCE,
                    "latest_price": latest_close,
                    "latest_trend": latest_trend,
                    "scanned_symbols_status": scanned_symbols_status,
                    "scan_total": total_symbols,
                    "scan_count": scanned_count,
                    "scan_skipped": skipped_count,
                    "trading_mode": self.config.get("trading_mode", "paper"),
                    "portfolio_margin": self.config.get("portfolio_margin", False),
                    "binance_auth_status": self.binance_auth_status,
                    "binance_auth_source": self.binance_auth_source,
                    "binance_auth_message": self.binance_auth_message,
                    "binance_auth_mode": self.binance_auth_mode,
                    "scan_interval_secs": self.config.get("scan_interval_secs", 15),
                    "scan_last_broadcast_at": int(time.time() * 1000),
                    "trade_history": self.trade_history
                }
            })
        except Exception as e:
            logger.error(f"Error broadcasting state: {e}")

    def update_config(self, new_config: Dict):
        self.config.update(new_config)
        self.save_config()

        if new_config.get("trading_mode") == "live":
            self.log_message("Live trading selected. Initializing Binance client after config update.", "info")
            self.init_binance_client()
        elif new_config.get("trading_mode") == "paper":
            self.log_message("Paper trading selected. Disabling Binance client if active.", "info")
            self.client = None
        elif self.config.get("trading_mode") == "live" and (
            "binance_api_key" in new_config or "binance_api_secret" in new_config or "testnet" in new_config
        ):
            self.log_message("Binance credentials or testnet flag updated while live mode is enabled. Reinitializing client.", "info")
            self.init_binance_client()

        logger.info("Configuration updated.")

    def log_message(self, message: str, level: str = "info"):
        if level == "error":
            logger.error(message)
        else:
            logger.info(message)
        
        # Broadcast immediately to frontend if callback is set
        if self.websocket_broadcast_callback:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.websocket_broadcast_callback({
                    "type": "log",
                    "data": {
                        "time": int(time.time() * 1000),
                        "level": level.upper(),
                        "message": message
                    }
                }))
            except RuntimeError:
                pass

    def _set_auth_status(self, status: str, source: Optional[str], message: str, mode: Optional[str] = None):
        self.binance_auth_status = status
        self.binance_auth_source = source
        self.binance_auth_message = message
        self.binance_auth_mode = mode

    def is_placeholder_key(self, key: Optional[str]) -> bool:
        if not key:
            return True
        normalized = key.strip().lower()
        return normalized in {
            "testkey",
            "testsecret",
            "your_api_key",
            "your_api_secret",
            "replace_me",
            "xxxxx",
            "00000",
            "12345",
            "null",
            "none"
        }

    def load_env_keys(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        env_key = os.environ.get("BINANCE_KEY") or os.environ.get("BINANCE_API_KEY")
        env_secret = os.environ.get("BINANCE_SECRET") or os.environ.get("BINANCE_API_SECRET")
        if env_key and env_secret and not (
            self.is_placeholder_key(env_key) or self.is_placeholder_key(env_secret)
        ):
            os.environ.setdefault("BINANCE_API_KEY", env_key)
            os.environ.setdefault("BINANCE_KEY", env_key)
            os.environ.setdefault("BINANCE_API_SECRET", env_secret)
            os.environ.setdefault("BINANCE_SECRET", env_secret)
            logger.info("Loaded Binance API keys from environment variables.")
            return env_key, env_secret, "environment variables"

        search_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.local"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local"),
            ".env.local",
            ".env"
        ]
        for path in search_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        key = None
                        secret = None
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            if "=" in line:
                                k, v = line.split("=", 1)
                                k = k.strip()
                                v = v.strip().strip("'").strip('"')
                                if k in ["BINANCE_KEY", "BINANCE_API_KEY"]:
                                    key = v
                                elif k in ["BINANCE_SECRET", "BINANCE_API_SECRET"]:
                                    secret = v
                        if key and secret and not (
                            self.is_placeholder_key(key) or self.is_placeholder_key(secret)
                        ):
                            os.environ.setdefault("BINANCE_API_KEY", key)
                            os.environ.setdefault("BINANCE_KEY", key)
                            os.environ.setdefault("BINANCE_API_SECRET", secret)
                            os.environ.setdefault("BINANCE_SECRET", secret)
                            logger.info(f"Loaded Binance API keys from {path}")
                            return key, secret, path
                except Exception as e:
                    logger.error(f"Error reading env file at {path}: {e}")
        logger.info("No Binance API keys found in environment or .env file search paths")
        return None, None, None

    def init_binance_client(self):
        api_key = self.config.get("binance_api_key")
        api_secret = self.config.get("binance_api_secret")
        testnet = self.config.get("testnet", True)
        trading_mode = self.config.get("trading_mode", "paper")
        portfolio_margin = self.config.get("portfolio_margin", False)
        market_type = self.config.get("market_type", "futures")

        self.binance_auth_status = "pending"
        self.binance_auth_source = None
        self.binance_auth_message = None
        self.binance_auth_mode = None
        
        # Treat fake placeholder values as absent so they don't block valid env/.env keys.
        if self.is_placeholder_key(api_key) or self.is_placeholder_key(api_secret):
            if api_key or api_secret:
                self.log_message(
                    "Detected placeholder Binance keys in config.json; ignoring them and falling back to environment or .env.",
                    "warning"
                )
            api_key = None
            api_secret = None

        env_key = env_secret = source = None
        if not api_key or not api_secret:
            # Fallback to environment variables or .env file
            env_key, env_secret, source = self.load_env_keys()
            if env_key and env_secret:
                api_key = env_key
                api_secret = env_secret
                self.log_message("Automatically loaded Binance API keys from environment or .env file.")
                if self.is_placeholder_key(self.config.get("binance_api_key")) or self.is_placeholder_key(self.config.get("binance_api_secret")):
                    self.config["binance_api_key"] = ""
                    self.config["binance_api_secret"] = ""
                    self.save_config()
                    self.log_message("Removed placeholder Binance credentials from config.json.", "info")
        
        if api_key and api_secret:
            if self.config.get("binance_api_key") and self.config.get("binance_api_secret") and not (
                self.is_placeholder_key(self.config.get("binance_api_key")) or
                self.is_placeholder_key(self.config.get("binance_api_secret"))
            ):
                source = "config.json"
            elif source is None:
                source = "unknown source"
            self.log_message(f"Initializing Binance client with keys loaded from {source}.")
            try:
                self.client = Client(api_key, api_secret, testnet=testnet, requests_params={"timeout": 10})
                self.log_message("Binance Client initialized successfully.")
                verified = self.verify_binance_connection(source)
                if not verified and market_type == "futures" and not portfolio_margin:
                    self._try_portfolio_margin_fallback(source)
            except Exception as e:
                self.log_message(f"Failed to init Binance client with keys: {e}. Falling back to public endpoints.", "warning")
                self.client = None
                if trading_mode == "live":
                    self.log_message(
                        "Live trading is enabled but Binance client failed to initialize. "
                        "Please verify API credentials and permissions.",
                        "warning"
                    )
                else:
                    self.log_message("Live mode is not enabled; operating in paper/public mode.", "info")
        else:
            if trading_mode == "live":
                self.log_message(
                    "Live trading is enabled but Binance API keys are missing. "
                    "Please configure keys to enable real orders.",
                    "warning"
                )
            else:
                self.log_message("No API keys found. Operating in public endpoint monitoring mode (Paper trading only).")
            self.client = None

    def _is_papi_unauthorized(self, exception: Exception) -> bool:
        if isinstance(exception, requests.exceptions.HTTPError):
            response = getattr(exception, 'response', None)
            if response is not None:
                if response.status_code == 401:
                    return True
                body = response.text.lower()
                if 'invalid api-key' in body or 'invalid api-key, ip, or permissions' in body:
                    return True
        return False

    def _try_portfolio_margin_fallback(self, source: str) -> bool:
        try:
            self.log_message(
                "Standard futures auth failed. Attempting Portfolio Margin API auth as a fallback.",
                "info"
            )
            result = self._make_papi_request("GET", "/papi/v1/balance")
            if result is not None:
                self.config["portfolio_margin"] = True
                self.save_config()
                fallback_msg = (
                    f"Binance credentials appear valid for Portfolio Margin. "
                    f"Enabled portfolio_margin=true and switched live trading to Portfolio Margin mode. Keys were loaded from {source}."
                )
                self._set_auth_status("success", source, fallback_msg, mode="portfolio_margin")
                self.log_message(fallback_msg, "info")
                return True
        except Exception as e:
            self.log_message(
                f"Portfolio Margin fallback auth also failed: {e}",
                "warning"
            )
        return False

    def _make_papi_request(self, method: str, endpoint: str, params: dict = None) -> dict:
        """Helper to sign and execute REST requests to the Binance Portfolio Margin API."""
        api_key = self.config.get("binance_api_key")
        api_secret = self.config.get("binance_api_secret")
        
        if self.is_placeholder_key(api_key) or self.is_placeholder_key(api_secret):
            api_key = None
            api_secret = None

        if not api_key or not api_secret:
            env_key, env_secret, _ = self.load_env_keys()
            if env_key and env_secret:
                api_key = env_key
                api_secret = env_secret
                
        if not api_key or not api_secret:
            raise ValueError("Binance API keys are missing.")
            
        base_url = "https://papi.binance.com"
        if params is None:
            params = {}
            
        # Ensure timestamp and recvWindow are present
        timestamp = int(time.time() * 1000)
        payload = {**params, "recvWindow": 10000, "timestamp": timestamp}
        
        # Sort and construct query string (percent-encode to handle non-ASCII/special characters)
        from urllib.parse import urlencode
        query_string = urlencode(sorted(payload.items()))
        
        # Calculate HMAC signature
        signature = hmac.new(
            api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        headers = {
            "X-MBX-APIKEY": api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        url = f"{base_url}{endpoint}"
        
        try:
            if method == "GET" or method == "DELETE":
                url = f"{url}?{query_string}&signature={signature}"
                res = requests.request(method, url, headers=headers, timeout=10)
            else: # POST, PUT, etc.
                post_data = f"{query_string}&signature={signature}"
                res = requests.request(method, url, headers=headers, data=post_data, timeout=10)
                
            res.raise_for_status()
            return res.json()
        except requests.exceptions.HTTPError as e:
            resp_text = res.text if 'res' in locals() else 'No response'
            if self._is_api_unauthorized(e):
                self.log_message("Portfolio Margin request unauthorized. Falling back if possible.", "warning")
            logger.error(f"PAPI API Request failed: {e}. Response body: {resp_text}")
            raise e

    def _is_api_unauthorized(self, exception: Exception) -> bool:
        text = str(exception).lower()
        if 'invalid api-key' in text or 'invalid api-key, ip, or permissions' in text or '401' in text or 'unauthorized' in text:
            return True
        if isinstance(exception, (BinanceAPIException, BinanceRequestException)):
            status = getattr(exception, 'status_code', None)
            if status == 401:
                return True
        return False

    def disable_live_mode(self, reason: str):
        if self.config.get("trading_mode") != "live":
            return
        self.config["trading_mode"] = "paper"
        self.save_config()
        self.client = None
        self.log_message(f"Disabling live trading due to authentication failure: {reason}. Switched to paper mode.", "warning")

    def verify_binance_connection(self, source: str = "unknown source") -> bool:
        if self.config.get("trading_mode") != "live":
            self._set_auth_status("unknown", source, "Live trading is not enabled.", None)
            return False

        if not self.client:
            msg = (
                "Binance client is not initialized for live trading. Live mode remains enabled and will retry later."
            )
            self.log_message(msg, "warning")
            self._set_auth_status("failed", source, msg, None)
            return False

        market_type = self.config.get("market_type", "futures")
        portfolio_margin = self.config.get("portfolio_margin", False)
        mode = "portfolio_margin" if portfolio_margin else ("futures" if market_type == "futures" else "spot")

        try:
            if portfolio_margin:
                self._make_papi_request("GET", "/papi/v1/balance")
            elif market_type == "futures":
                self.client.futures_account_balance()
            else:
                self.client.get_asset_balance(asset="USDT")
        except Exception as e:
            if self._is_api_unauthorized(e):
                msg = (
                    f"Binance API authentication failed during validation with keys loaded from {source}: {e}. "
                    "Live mode remains enabled so you can correct credentials or permissions."
                )
                self.log_message(msg, "error")
                self._set_auth_status("failed", source, msg, mode=mode)
            else:
                msg = (
                    f"Binance client validation failed with keys loaded from {source}: {e}. "
                    "Live mode remains enabled and will retry later."
                )
                self.log_message(msg, "warning")
                self._set_auth_status("warning", source, msg, mode=mode)
            return False

        msg = f"Binance API authentication verified successfully with keys loaded from {source}."
        self.log_message(msg, "info")
        self._set_auth_status("success", source, msg, mode=mode)
        return True

    def get_live_balance(self) -> float:
        trading_mode = self.config.get("trading_mode", "paper")
        if trading_mode != "live":
            return self.paper_balance
            
        portfolio_margin = self.config.get("portfolio_margin", False)
        
        try:
            if portfolio_margin:
                try:
                    res = self._make_papi_request("GET", "/papi/v1/balance")
                    if isinstance(res, list):
                        for b in res:
                            if b.get('asset') == 'USDT':
                                return float(b.get('totalWalletBalance', 0.0))
                    elif isinstance(res, dict):
                        if res.get('asset') == 'USDT':
                            return float(res.get('totalWalletBalance', 0.0))
                except requests.exceptions.HTTPError as e:
                    if self._is_papi_unauthorized(e):
                        self.log_message("Portfolio Margin PAPI unauthorized; falling back to standard futures balance retrieval for this cycle.", "warning")
                        portfolio_margin = False
                    else:
                        logger.error(f"Error fetching live Binance balance: {e}")
                        return self.paper_balance
            if not portfolio_margin:
                if not self.client:
                    return self.paper_balance
                market_type = self.config.get("market_type", "futures")
                if market_type == "futures":
                    balances = self.client.futures_account_balance()
                    for b in balances:
                        if b['asset'] == 'USDT':
                            return float(b['balance'])
                else: # spot
                    b = self.client.get_asset_balance(asset='USDT')
                    if b:
                        return float(b['free']) + float(b['locked'])
        except Exception as e:
            if self._is_api_unauthorized(e):
                self.log_message(
                    "Binance API unauthorized while fetching live balance. Live mode remains enabled so user can correct credentials or permissions.",
                    "error"
                )
                return self.paper_balance
            logger.error(f"Error fetching live Binance balance: {e}")
        
        return self.paper_balance

    def get_exchange_positions(self) -> Dict[str, Dict]:
        """
        Retrieves actual open positions from the exchange (Binance Portfolio Margin or Futures).
        """
        trading_mode = self.config.get("trading_mode", "paper")
        if trading_mode != "live":
            return self.active_trades
            
        portfolio_margin = self.config.get("portfolio_margin", False)
        exchange_positions = {}
        
        try:
            positions_raw = []
            if portfolio_margin:
                try:
                    res = self._make_papi_request("GET", "/papi/v1/um/positionRisk")
                    if isinstance(res, list):
                        positions_raw = res
                except requests.exceptions.HTTPError as e:
                    if self._is_papi_unauthorized(e):
                        self.log_message("Portfolio Margin PAPI unauthorized; falling back to standard futures position retrieval for this cycle.", "warning")
                        portfolio_margin = False
                    else:
                        raise
            if not portfolio_margin:
                if self.client:
                    market_type = self.config.get("market_type", "futures")
                    if market_type == "futures":
                        positions_raw = self.client.futures_position_information()
                        
            # Parse raw positions
            for pos in positions_raw:
                symbol = pos.get('symbol')
                position_amt = float(pos.get('positionAmt', 0.0) or pos.get('positionAmount', 0.0) or 0.0)
                if position_amt != 0.0:
                    entry_price = float(pos.get('entryPrice', 0.0) or 0.0)
                    side = 'long' if position_amt > 0 else 'short'
                    size = abs(position_amt)
                    
                    sl = 0.0
                    tp = 0.0
                    entry_time = int(time.time() * 1000)
                    risk_amount = 0.0
                    
                    if symbol in self.active_trades:
                        local_trade = self.active_trades[symbol]
                        sl = local_trade.get('sl', 0.0)
                        tp = local_trade.get('tp', 0.0)
                        entry_time = local_trade.get('entry_time', entry_time)
                        risk_amount = local_trade.get('risk_amount', 0.0)
                    
                    exchange_positions[symbol] = {
                        'symbol': symbol,
                        'type': side,
                        'entry_price': entry_price,
                        'sl': sl,
                        'tp': tp,
                        'size': size,
                        'risk_amount': risk_amount,
                        'entry_time': entry_time,
                        'live': True
                    }
                    
            if isinstance(positions_raw, list):
                self.active_trades = exchange_positions
                self.save_trades()
                
        except Exception as e:
            if self._is_api_unauthorized(e):
                self.log_message(
                    "Binance API unauthorized while fetching live positions. Live mode remains enabled so user can correct credentials or permissions.",
                    "error"
                )
                return self.active_trades
            logger.error(f"Error fetching live exchange positions: {e}")
            
        return self.active_trades

    def has_recent_structure(self, smc_res: Dict, current_idx: int, direction: str, lookback: int = 3) -> bool:
        """
        Returns True if a recent bullish/bearish BOS or CHoCH occurred within the lookback window.
        """
        structures = []
        structures.extend(smc_res.get('bos', []))
        structures.extend(smc_res.get('choch', []))
        for struct in structures:
            if struct.get('type') == direction:
                idx = int(struct.get('idx', -999))
                if current_idx - lookback <= idx <= current_idx:
                    return True
        return False

    def check_daily_drawdown(self) -> bool:
        """
        Calculates the net realized PnL of all trades closed today.
        Returns True if the drawdown exceeds the daily drawdown limit.
        """
        limit_pct = self.config.get("daily_drawdown_limit_pct", 0.0)
        if limit_pct <= 0.0:
            return False
            
        from datetime import datetime, time as dt_time
        now = datetime.now()
        start_of_today = datetime.combine(now.date(), dt_time.min)
        start_of_today_ms = int(start_of_today.timestamp() * 1000)
        
        daily_pnl = 0.0
        for t in self.trade_history:
            exit_time = t.get('exit_time', 0)
            if exit_time >= start_of_today_ms:
                daily_pnl += t.get('pnl', 0.0)
                
        start_of_day_balance = self.paper_balance - daily_pnl
        if start_of_day_balance <= 0:
            start_of_day_balance = DEFAULT_INITIAL_BALANCE
            
        if daily_pnl < 0:
            drawdown_pct = (-daily_pnl / start_of_day_balance) * 100.0
            if drawdown_pct >= limit_pct:
                return True
        return False

    def parse_klines(self, klines) -> Optional[pd.DataFrame]:
        if not klines or not isinstance(klines, list):
            return None
        try:
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            numeric_cols = [
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume'
            ]
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            df['timestamp'] = df['timestamp'].astype('Int64')
            df['close_time'] = df['close_time'].astype('Int64')
            return df
        except Exception as e:
            logger.warning(f"Failed to parse klines: {e}")
            return None

    async def fetch_all_klines(self, symbols: List[str]) -> Dict[str, pd.DataFrame]:
        """Fetch historical klines for multiple symbols in controlled batches."""
        max_concurrency = min(self.config.get("max_fetch_concurrency", 10), len(symbols))
        batch_delay = self.config.get("fetch_batch_delay", 2)
        semaphore = asyncio.Semaphore(max_concurrency)

        results = {}
        for start in range(0, len(symbols), max_concurrency):
            batch = symbols[start:start + max_concurrency]
            tasks = [self.fetch_klines_for_symbol(symbol, semaphore) for symbol in batch]
            batch_results = await asyncio.gather(*tasks)
            results.update({symbol: df for symbol, df in zip(batch, batch_results) if df is not None})
            if start + max_concurrency < len(symbols):
                await asyncio.sleep(batch_delay)
        return results

    async def fetch_klines_for_symbol(self, symbol: str, semaphore: asyncio.Semaphore) -> Optional[pd.DataFrame]:
        """Fetch klines wrapped in a background thread with concurrency control."""
        async with semaphore:
            return await asyncio.to_thread(self._fetch_klines_sync, symbol)

    def _fetch_klines_sync(self, symbol: str) -> Optional[pd.DataFrame]:
        timeframe = self.config.get("timeframe", "15m")
        limit = 500 # Need enough data for rolling metrics & swings
        market_type = self.config.get("market_type", "futures")
        testnet = self.config.get("testnet", True)

        # 1. Try authenticated client if available
        if self.client:
            try:
                if market_type == "futures":
                    klines = self.client.futures_klines(symbol=symbol, interval=timeframe, limit=limit)
                else:
                    klines = self.client.get_klines(symbol=symbol, interval=timeframe, limit=limit)
                return self.parse_klines(klines)
            except Exception:
                pass

        # 2. Try public REST endpoints fallback
        try:
            if market_type == "futures":
                if testnet:
                    url = f"https://testnet.binancefuture.com/fapi/v1/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
                else:
                    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
            else:
                if testnet:
                    url = f"https://testnet.binance.vision/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
                else:
                    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"

            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                klines = response.json()
                return self.parse_klines(klines)
            logger.warning(f"Failed to fetch klines for {symbol}: {response.status_code} {response.text[:200]}")
        except Exception as e:
            logger.warning(f"Failed to fetch klines for {symbol} via public endpoint: {e}")
            return None

        return None

    async def start(self):
        if self.running:
            return
        
        self.config = self.load_config()
        self.config["running"] = True
        self.save_config()
        
        self.running = True
        self.init_binance_client()
        
        # Dynamically fetch top liquid symbols if enabled without blocking startup
        if self.config.get("dynamic_scan", True):
            asyncio.create_task(self.refresh_top_symbols())
            
        self.log_message(f"Starting AICryptoSMC Bot on {len(self.config.get('symbols', ['BTCUSDT']))} symbols...")
        
        self.task = asyncio.create_task(self.trading_loop())

    async def refresh_top_symbols(self):
        try:
            self.log_message("Fetching top liquid USDT pairs from Binance...")
            limit = self.config.get("max_scanned_coins", 100)
            market_type = self.config.get("market_type", "futures")
            
            # Fetch 24h ticker data
            if market_type == "futures":
                url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
            else:
                url = "https://api.binance.com/api/v3/ticker/24hr"
                
            response = await asyncio.to_thread(requests.get, url, timeout=10)
            if response.status_code == 200:
                tickers = response.json()
                usdt_pairs = []
                for t in tickers:
                    symbol = t['symbol']
                    # Keep only USDT pairs
                    if symbol.endswith('USDT'):
                        # Filter leverage/stable/fiat tokens
                        if any(x in symbol for x in ["UP", "DOWN", "BEAR", "BULL", "USDC", "BUSD", "EUR", "GBP"]):
                            continue
                        
                        # Use quoteVolume (USDT volume)
                        quote_vol = float(t.get('quoteVolume', 0.0))
                        usdt_pairs.append((symbol, quote_vol))
                
                # Sort by volume descending
                usdt_pairs.sort(key=lambda x: x[1], reverse=True)
                top_symbols = [x[0] for x in usdt_pairs[:limit]]
                
                if top_symbols:
                    self.config["symbols"] = top_symbols
                    selected = self.config.get("selected_symbol", "BTCUSDT")
                    if selected not in top_symbols:
                        self.config["selected_symbol"] = top_symbols[0]
                    self.save_config()
                    self.log_message(f"Successfully loaded top {len(top_symbols)} liquid USDT markets.")
                else:
                    self.log_message("No top symbols found, using default list.", "error")
            else:
                self.log_message(f"Failed to fetch ticker data: {response.text}", "error")
        except Exception as e:
            self.log_message(f"Error fetching top liquid symbols: {e}", "error")

    async def stop(self, is_shutdown=False):
        if not self.running:
            return
        
        self.running = False
        if not is_shutdown:
            self.config["running"] = False
            self.save_config()
        
        self.log_message("Stopping AICryptoSMC Bot...")
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
            
        self.log_message("Bot stopped.")

    async def trading_loop(self):
        sleep_interval = self.config.get("scan_interval_secs")
        if sleep_interval is None or not isinstance(sleep_interval, (int, float)) or sleep_interval <= 0:
            sleep_interval = 15
        if len(self.config.get("symbols", [])) > 100:
            sleep_interval = max(sleep_interval, 30)
        self.config["scan_interval_secs"] = sleep_interval
        self.save_config()
        self.log_message(f"Entering main execution loop with scan interval={sleep_interval}s.")
        
        while self.running:
            try:
                start_time = time.time()
                # Load configuration dynamically to detect changes (like symbols list, timeframe)
                self.config = self.load_config()
                symbols = self.config.get("symbols", [self.config.get("symbol", "BTCUSDT")])
                timeframe = self.config.get("timeframe", "15m")
                
                # 1. Fetch data concurrently
                dfs = await self.fetch_all_klines(symbols)
                if not dfs:
                    self.log_message("No candlestick data could be retrieved. Retrying in 10s...", "error")
                    await asyncio.sleep(10)
                    continue
                
                self.dfs = dfs
                
                # Make sure we keep self.df updated with the selected/default symbol
                selected_symbol = self.config.get("selected_symbol", "BTCUSDT")
                
                scanned_symbols_status = {}
                
                # 2. Iterate and process each symbol
                for symbol, df in list(dfs.items()):
                    # Check if we have sufficient candles for SMC calculation
                    min_candles = max(self.config.get("m_range", 5) + 5, 20)
                    if df is None or len(df) < min_candles:
                        logger.warning(f"Skipping {symbol}: insufficient data (have {len(df) if df is not None else 0} candles, need {min_candles})")
                        dfs.pop(symbol, None)
                        continue
                    
                    # Check if we have new candle close
                    latest_candle_time = int(df.iloc[-1]['timestamp'])
                    last_time = self.last_candle_times.get(symbol, 0)
                    is_new_candle = latest_candle_time > last_time
                    
                    # Run SMC calculations off the main event loop
                    smc_res = await asyncio.to_thread(
                        calculate_smc,
                        df,
                        N=self.config.get("n_swing", 2),
                        X_impulse=self.config.get("x_impulse", 2.0),
                        M_range=self.config.get("m_range", 5)
                    )
                    
                    # Save results in dfs
                    dfs[symbol] = smc_res['df']
                    
                    # Process signals
                    self.process_tick(symbol, smc_res, is_new_candle)
                    
                    if is_new_candle:
                        self.last_candle_times[symbol] = latest_candle_time
                        
                    # Save status info for UI sidebar
                    latest_candle = smc_res['df'].iloc[-1]
                    scanned_symbols_status[symbol] = {
                        "price": float(latest_candle['close']),
                        "trend": latest_candle.get('trend', 'neutral'),
                        "has_active_trade": symbol in self.active_trades,
                        "is_swing_high": bool(latest_candle.get('is_swing_high', False)),
                        "is_swing_low": bool(latest_candle.get('is_swing_low', False))
                    }
                
                # Update self.df to the processed selected/fallback dataframe
                if selected_symbol in dfs:
                    self.df = dfs[selected_symbol]
                elif dfs:
                    self.df = next(iter(dfs.values()))
                
                # 3. Broadcast state to UI
                await self.broadcast_current_state()

                # Log scan tick summary
                elapsed = time.time() - start_time
                self.log_message(f"[Scanner] Scanned {len(dfs)}/{len(symbols)} symbols concurrently in {elapsed:.2f}s. Active positions: {len(self.active_trades)}.")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in trading loop")
                self.log_message(f"Error in trading loop: {e}", "error")
                await asyncio.sleep(10)
                
            await asyncio.sleep(sleep_interval)

    def process_tick(self, symbol: str, smc_res: Dict, is_new_candle: bool):
        df = smc_res['df']
        current_candle = df.iloc[-1]
        current_price = float(current_candle['close'])
        current_high = float(current_candle['high'])
        current_low = float(current_candle['low'])
        current_time = int(current_candle['timestamp'])
        
        # 1. Manage Active Trade for this symbol
        if symbol in self.active_trades:
            trade = self.active_trades[symbol]
            trade_type = trade['type']
            sl = trade['sl']
            tp = trade['tp']
            size = trade['size']
            entry_price = trade['entry_price']
            
            # Update Peak Price for Trailing Stop
            peak_price = trade.get('peak_price', entry_price)
            if trade_type == 'long':
                trade['peak_price'] = max(peak_price, current_high)
            elif trade_type == 'short':
                trade['peak_price'] = min(peak_price, current_low)
            peak_price = trade['peak_price']
            
            # Trailing Stop Loss Adjustment
            trailing_activation = self.config.get("trailing_stop_activation_pct", 0.0)
            trailing_distance = self.config.get("trailing_stop_distance_pct", 0.0)
            
            if trailing_activation > 0.0 and trailing_distance > 0.0:
                if trade_type == 'long':
                    profit_pct = ((peak_price - entry_price) / entry_price) * 100.0
                    if profit_pct >= trailing_activation:
                        trail_sl = peak_price * (1.0 - (trailing_distance / 100.0))
                        if trail_sl > sl:
                            trade['sl'] = trail_sl
                            self.log_message(f"[{symbol}] Trailing Stop Loss moved up to {trail_sl:.4f}")
                            self.save_trades()
                elif trade_type == 'short':
                    profit_pct = ((entry_price - peak_price) / entry_price) * 100.0
                    if profit_pct >= trailing_activation:
                        trail_sl = peak_price * (1.0 + (trailing_distance / 100.0))
                        if sl == 0.0 or trail_sl < sl:
                            trade['sl'] = trail_sl
                            self.log_message(f"[{symbol}] Trailing Stop Loss moved down to {trail_sl:.4f}")
                            self.save_trades()

            # Opposing Sweep Exit
            opposing_sweep_enabled = self.config.get("opposing_sweep_exit_enabled", False)
            opposing_sweep_min_adverse_pct = self.config.get("opposing_sweep_min_adverse_pct", 0.0)
            if opposing_sweep_enabled and is_new_candle and len(df) > 2:
                closed_idx = len(df) - 2
                sweeps = smc_res.get('liquidity_grabs', [])
                sweep = next((sw for sw in sweeps if sw['idx'] == closed_idx), None)
                if sweep:
                    sweep_type = sweep['type']
                    if trade_type == 'long' and sweep_type == 'bearish_sweep':
                        adverse_pct = ((entry_price - current_price) / entry_price) * 100.0
                        if adverse_pct < opposing_sweep_min_adverse_pct:
                            self.log_message(
                                f"[{symbol}] Bearish sweep detected but adverse move {adverse_pct:.3f}% is below opposing sweep threshold {opposing_sweep_min_adverse_pct:.3f}%. Holding LONG."
                            )
                        else:
                            self.log_message(
                                f"[{symbol}] Opposing Bearish Sweep detected at {current_price}. Exiting LONG trade early after {adverse_pct:.3f}% adverse move."
                            )
                            pnl = (current_price - entry_price) * size
                            self.paper_balance += pnl
                            self.close_trade(symbol, current_price, pnl, "OPPOSING_SWEEP")
                            return
                    elif trade_type == 'short' and sweep_type == 'bullish_sweep':
                        adverse_pct = ((current_price - entry_price) / entry_price) * 100.0
                        if adverse_pct < opposing_sweep_min_adverse_pct:
                            self.log_message(
                                f"[{symbol}] Bullish sweep detected but adverse move {adverse_pct:.3f}% is below opposing sweep threshold {opposing_sweep_min_adverse_pct:.3f}%. Holding SHORT."
                            )
                        else:
                            self.log_message(
                                f"[{symbol}] Opposing Bullish Sweep detected at {current_price}. Exiting SHORT trade early after {adverse_pct:.3f}% adverse move."
                            )
                            pnl = (entry_price - current_price) * size
                            self.paper_balance += pnl
                            self.close_trade(symbol, current_price, pnl, "OPPOSING_SWEEP")
                            return

            # Momentum Stall Exit
            stall_candles = self.config.get("stall_exit_candles", 0)
            stall_min_move = self.config.get("stall_exit_min_move_pct", 0.0)
            if stall_candles > 0 and len(df) > stall_candles:
                entry_candle_idx = trade.get('entry_candle_idx', len(df) - 1)
                current_idx = len(df) - 1
                if current_idx - entry_candle_idx >= stall_candles:
                    last_candles = df.iloc[-stall_candles:]
                    price_min = last_candles['low'].min()
                    price_max = last_candles['high'].max()
                    range_pct = ((price_max - price_min) / price_min) * 100.0
                    vol_declining = last_candles['volume'].iloc[-1] < last_candles['volume'].mean()
                    
                    if range_pct < stall_min_move and vol_declining:
                        self.log_message(f"[{symbol}] Momentum stall detected (range {range_pct:.2f}% < {stall_min_move}%, low volume). Exiting trade early.")
                        if trade_type == 'long':
                            pnl = (current_price - entry_price) * size
                        else:
                            pnl = (entry_price - current_price) * size
                        self.paper_balance += pnl
                        self.close_trade(symbol, current_price, pnl, "STALL")
                        return

            # Breakeven Adjustment
            breakeven_trigger = self.config.get("breakeven_trigger", 1.0)
            if not trade.get("breakeven_set", False) and breakeven_trigger > 0:
                if trade_type == 'long':
                    if current_high >= entry_price + (breakeven_trigger * (entry_price - sl)):
                        trade['sl'] = entry_price
                        trade['breakeven_set'] = True
                        self.log_message(f"[{symbol}] Moving SL to Breakeven at {entry_price} for Long trade.")
                        self.save_trades()
                elif trade_type == 'short':
                    if current_low <= entry_price - (breakeven_trigger * (sl - entry_price)):
                        trade['sl'] = entry_price
                        trade['breakeven_set'] = True
                        self.log_message(f"[{symbol}] Moving SL to Breakeven at {entry_price} for Short trade.")
                        self.save_trades()

            # Hard loss cap exit
            max_trade_loss_pct = self.config.get("max_trade_loss_pct", 0.0)
            if max_trade_loss_pct > 0.0:
                if trade_type == 'long':
                    loss_pct = ((entry_price - current_low) / entry_price) * 100.0
                    if loss_pct >= max_trade_loss_pct:
                        pnl = (current_low - entry_price) * size
                        self.paper_balance += pnl
                        self.log_message(f"[{symbol}] HARD STOP triggered at {current_low:.8f} after {loss_pct:.2f}% loss. Exiting LONG trade.")
                        self.close_trade(symbol, current_low, pnl, "HARD_STOP")
                        return
                elif trade_type == 'short':
                    loss_pct = ((current_high - entry_price) / entry_price) * 100.0
                    if loss_pct >= max_trade_loss_pct:
                        pnl = (entry_price - current_high) * size
                        self.paper_balance += pnl
                        self.log_message(f"[{symbol}] HARD STOP triggered at {current_high:.8f} after {loss_pct:.2f}% loss. Exiting SHORT trade.")
                        self.close_trade(symbol, current_high, pnl, "HARD_STOP")
                        return

            # Read SL again
            sl = trade['sl']

            # Check if hit SL or TP
            if trade_type == 'long':
                if sl > 0.0 and current_low <= sl:
                    # SL Hit
                    pnl = (sl - entry_price) * size
                    self.paper_balance += pnl
                    self.log_message(f"[{symbol}] LONG Trade SL Hit! Exit price: {sl}, PnL: {pnl:.2f} USD")
                    self.close_trade(symbol, sl, pnl, "SL" if pnl < 0 else "BE")
                elif tp > 0.0 and current_high >= tp:
                    # TP Hit
                    pnl = (tp - entry_price) * size
                    self.paper_balance += pnl
                    self.log_message(f"[{symbol}] LONG Trade TP Hit! Exit price: {tp}, PnL: {pnl:.2f} USD")
                    self.close_trade(symbol, tp, pnl, "TP")
            elif trade_type == 'short':
                if sl > 0.0 and current_high >= sl:
                    # SL Hit
                    pnl = (entry_price - sl) * size
                    self.paper_balance += pnl
                    self.log_message(f"[{symbol}] SHORT Trade SL Hit! Exit price: {sl}, PnL: {pnl:.2f} USD")
                    self.close_trade(symbol, sl, pnl, "SL" if pnl < 0 else "BE")
                elif tp > 0.0 and current_low <= tp:
                    # TP Hit
                    pnl = (entry_price - tp) * size
                    self.paper_balance += pnl
                    self.log_message(f"[{symbol}] SHORT Trade TP Hit! Exit price: {tp}, PnL: {pnl:.2f} USD")
                    self.close_trade(symbol, tp, pnl, "TP")
                    
        # 2. Check for entry triggers on new candle close
        elif is_new_candle and len(df) > 2:
            if self.check_daily_drawdown():
                self.log_message(f"[{symbol}] Daily drawdown limit reached. Skipping trade entry.", "warning")
                return

            max_active = self.config.get("max_active_trades", 5)
            if len(self.active_trades) >= max_active:
                # Max concurrent positions limit reached
                return

            # We look at the candle that just closed (index -2) to find sweeps & zones
            closed_idx = len(df) - 2
            closed_candle = df.iloc[closed_idx]
            
            # Check ADX filter
            adx_threshold = self.config.get("adx_threshold", 0.0)
            if adx_threshold > 0.0:
                candle_adx = closed_candle.get('adx', 0.0)
                if candle_adx < adx_threshold:
                    return

            closed_time = int(closed_candle['timestamp'])
            current_trend = closed_candle['trend']
            
            # Find sweeps at closed_idx
            sweeps = smc_res['liquidity_grabs']
            sweep = next((sw for sw in sweeps if sw['idx'] == closed_idx), None)
            
            if sweep:
                sweep_type = sweep['type']
                rr_ratio = self.config.get("rr_ratio", 2.0)
                risk_pct = self.config.get("risk_pct", 1.0)
                
                # LONG setup check
                if current_trend == 'uptrend' and sweep_type == 'bullish_sweep' and self.has_recent_structure(smc_res, closed_idx, 'bullish'):
                    sweep_low = sweep['wick_low']
                    demand_zones = [z for z in smc_res['demand_zones'] if z.get('active', True)]
                    matching_zone = None
                    
                    for zone in demand_zones:
                        if zone['start_idx'] < closed_idx:
                            # Sweep penetrated zone but close was above zone low
                            if sweep_low <= zone['high'] and float(closed_candle['close']) >= zone['low']:
                                matching_zone = zone
                                break
                                
                    if matching_zone:
                        entry_price = float(closed_candle['close'])
                        min_stop_dist = entry_price * 0.005  # Require at least 0.5% stop distance
                        raw_stop = sweep_low - (entry_price * 0.001)
                        stop_loss = min(raw_stop, entry_price - min_stop_dist)
                        risk_per_share = entry_price - stop_loss
                        
                        if risk_per_share > 0:
                            current_balance = self.get_live_balance()
                            risk_usd = current_balance * (risk_pct / 100.0)
                            size = risk_usd / risk_per_share
                            take_profit = entry_price + (rr_ratio * risk_per_share)
                            
                            self.open_trade(symbol, 'long', entry_price, stop_loss, take_profit, size, risk_usd, closed_time, closed_idx)

                # SHORT setup check
                elif current_trend == 'downtrend' and sweep_type == 'bearish_sweep' and self.has_recent_structure(smc_res, closed_idx, 'bearish'):
                    sweep_high = sweep['wick_high']
                    supply_zones = [z for z in smc_res['supply_zones'] if z.get('active', True)]
                    matching_zone = None
                    
                    for zone in supply_zones:
                        if zone['start_idx'] < closed_idx:
                            # Sweep penetrated zone but close was below zone high
                            if sweep_high >= zone['low'] and float(closed_candle['close']) <= zone['high']:
                                matching_zone = zone
                                break
                                
                    if matching_zone:
                        entry_price = float(closed_candle['close'])
                        min_stop_dist = entry_price * 0.005  # Require at least 0.5% stop distance
                        raw_stop = sweep_high + (entry_price * 0.001)
                        stop_loss = max(raw_stop, entry_price + min_stop_dist)
                        risk_per_share = stop_loss - entry_price
                        
                        if risk_per_share > 0:
                            current_balance = self.get_live_balance()
                            risk_usd = current_balance * (risk_pct / 100.0)
                            size = risk_usd / risk_per_share
                            take_profit = entry_price - (rr_ratio * risk_per_share)
                            
                            self.open_trade(symbol, 'short', entry_price, stop_loss, take_profit, size, risk_usd, closed_time, closed_idx)

    def get_symbol_precision(self, symbol: str, market_type: str = "futures") -> Tuple[int, int]:
        try:
            if not self.client:
                return 2, 4
            
            if market_type == "futures":
                info = self.client.futures_exchange_info()
                for s in info['symbols']:
                    if s['symbol'] == symbol:
                        price_precision = int(s['pricePrecision'])
                        qty_precision = int(s['quantityPrecision'])
                        for f in s.get('filters', []):
                            if f['filterType'] == 'PRICE_FILTER':
                                tick_size = float(f['tickSize'])
                                price_precision = int(round(-np.log10(tick_size)))
                            elif f['filterType'] == 'LOT_SIZE':
                                step_size = float(f['stepSize'])
                                qty_precision = int(round(-np.log10(step_size)))
                        return price_precision, qty_precision
            else:
                info = self.client.get_symbol_info(symbol)
                price_precision = 2
                qty_precision = 4
                for f in info['filters']:
                    if f['filterType'] == 'PRICE_FILTER':
                        tick_size = float(f['tickSize'])
                        price_precision = int(round(-np.log10(tick_size)))
                    elif f['filterType'] == 'LOT_SIZE':
                        step_size = float(f['stepSize'])
                        qty_precision = int(round(-np.log10(step_size)))
                return price_precision, qty_precision
        except Exception as e:
            logger.error(f"Error fetching symbol precision: {e}")
        return 2, 4

    def open_trade(self, symbol: str, trade_type: str, entry_price: float, sl: float, tp: float, size: float, risk_usd: float, entry_time: int, entry_candle_idx: int = 0):
        market_type = self.config.get("market_type", "futures")
        trading_mode = self.config.get("trading_mode", "paper")
        
        trade_details = {
            'symbol': symbol,
            'type': trade_type,
            'entry_time': entry_time,
            'entry_price': entry_price,
            'sl': sl,
            'tp': tp,
            'size': size,
            'risk_amount': risk_usd,
            'breakeven_set': False,
            'peak_price': entry_price,
            'entry_candle_idx': entry_candle_idx
        }
        self.active_trades[symbol] = trade_details
        
        self.log_message(f"[{symbol}] OPENED {trade_type.upper()} Trade. Entry: {entry_price}, SL: {sl:.4f}, TP: {tp:.4f}, Size: {size:.6f}")
        self.save_trades()
        if self.websocket_broadcast_callback:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.broadcast_current_state())
            except Exception:
                pass
        
        if trading_mode == "live" and self.client:
            try:
                # Fetch precision
                price_prec, qty_prec = self.get_symbol_precision(symbol, market_type)
                
                # Format quantity and price
                formatted_qty = round(size, qty_prec)
                formatted_sl = round(sl, price_prec)
                formatted_tp = round(tp, price_prec)
                
                qty_str = f"{formatted_qty:.{max(0, qty_prec)}f}" if qty_prec >= 0 else str(int(formatted_qty))
                sl_str = f"{formatted_sl:.{max(0, price_prec)}f}" if price_prec >= 0 else str(int(formatted_sl))
                tp_str = f"{formatted_tp:.{max(0, price_prec)}f}" if price_prec >= 0 else str(int(formatted_tp))
                
                if market_type == "futures":
                    portfolio_margin = self.config.get("portfolio_margin", False)
                    # Automatically adjust leverage to 20x to minimize initial margin and prevent failures
                    if portfolio_margin:
                        try:
                            self.log_message(f"[{symbol}] [PAPI] Setting leverage to 20x on exchange...")
                            self._make_papi_request("POST", "/papi/v1/um/leverage", {
                                "symbol": symbol,
                                "leverage": 20
                            })
                        except Exception as e:
                            self.log_message(f"[{symbol}] [PAPI] Failed to set leverage: {e}", "info")
                    elif self.client:
                        try:
                            self.client.futures_change_leverage(symbol=symbol, leverage=20)
                        except Exception as e:
                            pass

                    if portfolio_margin:
                        # Portfolio Margin order entry via PAPI
                        side = 'BUY' if trade_type == 'long' else 'SELL'
                        opp_side = 'SELL' if trade_type == 'long' else 'BUY'
                        try:
                            self.log_message(f"[{symbol}] [PAPI] Placing Live Futures {trade_type.upper()} Market Order for {qty_str}...")
                            entry_order = self._make_papi_request("POST", "/papi/v1/um/order", {
                                "symbol": symbol,
                                "side": side,
                                "type": "MARKET",
                                "quantity": qty_str
                            })
                            trade_details['entry_order_id'] = entry_order['orderId']
                            
                            self.log_message(f"[{symbol}] [PAPI] Placing Live Futures Stop Loss Order at {sl_str}...")
                            sl_order = self._make_papi_request("POST", "/papi/v1/um/algo/order", {
                                "symbol": symbol,
                                "side": opp_side,
                                "type": "STOP_MARKET",
                                "algoType": "CONDITIONAL",
                                "triggerPrice": sl_str,
                                "quantity": qty_str,
                                "reduceOnly": "true"
                            })
                            trade_details['sl_order_id'] = sl_order.get('algoId')
                            
                            self.log_message(f"[{symbol}] [PAPI] Placing Live Futures Take Profit Order at {tp_str}...")
                            tp_order = self._make_papi_request("POST", "/papi/v1/um/algo/order", {
                                "symbol": symbol,
                                "side": opp_side,
                                "type": "TAKE_PROFIT_MARKET",
                                "algoType": "CONDITIONAL",
                                "triggerPrice": tp_str,
                                "quantity": qty_str,
                                "reduceOnly": "true"
                            })
                            trade_details['tp_order_id'] = tp_order.get('algoId')
                        except requests.exceptions.HTTPError as e:
                            if self._is_papi_unauthorized(e):
                                self.log_message(f"[{symbol}] Portfolio Margin PAPI unauthorized during order entry; falling back to standard futures for this order.", "warning")
                                portfolio_margin = False
                            else:
                                raise
                    if not portfolio_margin:
                        # Standard Futures order entry
                        side = Client.SIDE_BUY if trade_type == 'long' else Client.SIDE_SELL
                        opp_side = Client.SIDE_SELL if trade_type == 'long' else Client.SIDE_BUY
                        
                        self.log_message(f"[{symbol}] Placing Live Futures {trade_type.upper()} Market Order for {formatted_qty}...")
                        
                        # 1. Place entry order
                        entry_order = self.client.futures_create_order(
                            symbol=symbol,
                            side=side,
                            type=Client.ORDER_TYPE_MARKET,
                            quantity=formatted_qty
                        )
                        trade_details['entry_order_id'] = entry_order['orderId']
                        
                        # 2. Place stop-loss order
                        self.log_message(f"[{symbol}] Placing Live Futures Stop Loss Order at {formatted_sl}...")
                        sl_order = self.client.futures_create_order(
                            symbol=symbol,
                            side=opp_side,
                            type='STOP_MARKET',
                            stopPrice=formatted_sl,
                            closePosition=True
                        )
                        trade_details['sl_order_id'] = sl_order['orderId']
                        
                        # 3. Place take-profit order
                        self.log_message(f"[{symbol}] Placing Live Futures Take Profit Order at {formatted_tp}...")
                        tp_order = self.client.futures_create_order(
                            symbol=symbol,
                            side=opp_side,
                            type='TAKE_PROFIT_MARKET',
                            stopPrice=formatted_tp,
                            closePosition=True
                        )
                        trade_details['tp_order_id'] = tp_order['orderId']
                    
                else: # Spot trading
                    if trade_type == 'short':
                        self.log_message(f"[{symbol}] Short trading is not supported on Live Spot. Margin/Futures required. Skipping actual order.", "error")
                    else:
                        self.log_message(f"[{symbol}] Placing Live Spot Long Market Buy for {formatted_qty}...")
                        entry_order = self.client.create_order(
                            symbol=symbol,
                            side=Client.SIDE_BUY,
                            type=Client.ORDER_TYPE_MARKET,
                            quantity=formatted_qty
                        )
                        trade_details['entry_order_id'] = entry_order['orderId']
                        
                        try:
                            self.log_message(f"[{symbol}] Placing Spot OCO Sell Order for SL {formatted_sl} and TP {formatted_tp}...")
                            formatted_sl_limit = round(formatted_sl * 0.995, price_prec)
                            
                            self.client.create_oco_order(
                                symbol=symbol,
                                side=Client.SIDE_SELL,
                                quantity=formatted_qty,
                                price=formatted_tp,
                                stopPrice=formatted_sl,
                                stopLimitPrice=formatted_sl_limit,
                                stopLimitTimeInForce='GTC'
                            )
                        except Exception as oco_err:
                            self.log_message(f"[{symbol}] Failed to place OCO order: {oco_err}. Managing SL/TP in-loop.", "error")
                            
            except Exception as e:
                self.log_message(f"[{symbol}] LIVE ORDER ENTRY FAILED: {e}", "error")
                # Reset active trade
                if symbol in self.active_trades:
                    del self.active_trades[symbol]
                self.save_trades()

    def close_trade(self, symbol: str, exit_price: float, raw_pnl: float, status: str):
        if symbol not in self.active_trades:
            return

        trade = self.active_trades[symbol]
        entry_price = trade['entry_price']
        size = trade['size']
        market_type = self.config.get("market_type", "futures")
        trading_mode = self.config.get("trading_mode", "paper")

        # Calculate realistic transaction fees (0.04% taker) and slippage (0.02%) per side
        fee_rate = 0.0004
        slippage_rate = 0.0002
        total_drag_rate = fee_rate + slippage_rate
        drag_amount = (entry_price + exit_price) * size * total_drag_rate

        # For true break-even exits, preserve the BE outcome rather than charging drag
        if raw_pnl == 0.0:
            pnl = 0.0
            drag_amount = 0.0
        else:
            pnl = raw_pnl - drag_amount
            self.paper_balance -= drag_amount

        peak_price = trade.get('peak_price', entry_price)
        if trade['type'] == 'long':
            peak_pnl = (peak_price - entry_price) * size
        else:
            peak_pnl = (entry_price - peak_price) * size
        regret_pnl = peak_pnl - pnl

        closed_trade = {
            **trade,
            'exit_time': int(time.time() * 1000),
            'exit_price': exit_price,
            'pnl': pnl,
            'peak_pnl': peak_pnl,
            'regret_pnl': regret_pnl,
            'status': status
        }

        self.trade_history.append(closed_trade)
        del self.active_trades[symbol]
        self.save_trades()
        self.log_message(
            f"[{symbol}] CLOSED Trade. PnL: {pnl:.2f} USD. Regret: {regret_pnl:.2f} USD. Account Balance: {self.paper_balance:.2f} USD"
        )

        if trading_mode == "live":
            try:
                if market_type == "futures":
                    portfolio_margin = self.config.get("portfolio_margin", False)
                    if portfolio_margin:
                        self.log_message(f"[{symbol}] [PAPI] Cancelling any open limit orders for this symbol on Futures...")
                        try:
                            self._make_papi_request("DELETE", "/papi/v1/um/allOpenOrders", {"symbol": symbol})
                        except Exception as e:
                            self.log_message(f"[{symbol}] [PAPI] Failed to cancel limit orders (possibly none open): {e}", "info")

                        self.log_message(f"[{symbol}] [PAPI] Cancelling any open algo orders for this symbol on Futures...")
                        try:
                            self._make_papi_request("DELETE", "/papi/v1/um/algo/allOpenOrders", {"symbol": symbol})
                        except Exception as e:
                            self.log_message(f"[{symbol}] [PAPI] Failed to cancel algo orders (possibly none open): {e}", "info")
                    elif self.client:
                        self.log_message(f"[{symbol}] Cancelling any open bracket orders for this symbol on Futures...")
                        self.client.futures_cancel_all_open_orders(symbol=symbol)
                elif self.client:
                    self.log_message(f"[{symbol}] Cancelling any open OCO orders for this symbol on Spot...")
                    open_orders = self.client.get_open_orders(symbol=symbol)
                    for order in open_orders:
                        self.client.cancel_order(symbol=symbol, orderId=order['orderId'])
            except Exception as e:
                self.log_message(f"[{symbol}] Error cancelling open orders on exit: {e}", "error")
