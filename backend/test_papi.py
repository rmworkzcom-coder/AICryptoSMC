import os
import time
import hmac
import hashlib
import requests
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_papi")

def test_portfolio_margin_balance():
    # Load credentials from .env.local in parent folder
    env_paths = [
        ".env.local",
        "../.env.local",
        ".env",
        "../.env"
    ]
    
    api_key = None
    secret_key = None
    
    for path in env_paths:
        if os.path.exists(path):
            logger.info(f"Loading env from {path}...")
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'").strip('"')
                        if k in ["BINANCE_KEY", "BINANCE_API_KEY"]:
                            api_key = v
                        elif k in ["BINANCE_SECRET", "BINANCE_API_SECRET"]:
                            secret_key = v
            break

    if not api_key or not secret_key:
        logger.error("Could not load API keys from environment/files.")
        return

    logger.info("Keys loaded. Sending request to https://papi.binance.com/papi/v1/balance...")
    
    base_url = "https://papi.binance.com"
    endpoint = "/papi/v1/balance"
    
    timestamp = int(time.time() * 1000)
    payload = {
        "recvWindow": 10000,
        "timestamp": timestamp
    }
    
    query_string = "&".join([f"{k}={v}" for k, v in sorted(payload.items())])
    
    signature = hmac.new(
        secret_key.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-MBX-APIKEY": api_key,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        logger.info(f"HTTP Status: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            logger.info("Success! Portfolio Margin balance response:")
            if isinstance(data, list):
                for b in data:
                    if b.get('asset') == 'USDT':
                        logger.info(f"USDT Wallet Balance: {b.get('totalWalletBalance')} USDT")
                        logger.info(f"UM Wallet Balance: {b.get('umWalletBalance')} USDT")
            else:
                logger.info(f"Response: {data}")
        else:
            logger.error(f"Failed with code {res.status_code}: {res.text}")
    except Exception as e:
        logger.error(f"Request failed: {e}")

if __name__ == "__main__":
    test_portfolio_margin_balance()
