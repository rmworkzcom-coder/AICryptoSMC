import os
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.local")

def run_comprehensive_matrix():
    print("====================================================")
    print("      BINANCE PORTFOLIO MARGIN COMPONENT MATRIX     ")
    print("====================================================")

    api_key = os.getenv("BINANCE_KEY")
    secret_key = os.getenv("BINANCE_SECRET")

    if not api_key or not secret_key:
        print("Critical Failure: API Keys are missing from your environment context.")
        return

    base_url = "https://papi.binance.com"

    def test_endpoint(name, method, endpoint, payload=None):
        if payload is None:
            payload = {}

        timestamp = int(time.time() * 1000)
        payload.update({"recvWindow": 10000, "timestamp": timestamp})

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

        try:
            if method == "GET":
                url = f"{base_url}{endpoint}?{query_string}&signature={signature}"
                res = requests.get(url, headers=headers)
            elif method == "POST":
                url = f"{base_url}{endpoint}"
                post_data = f"{query_string}&signature={signature}"
                res = requests.post(url, headers=headers, data=post_data)

            if res.status_code == 200:
                print(f"✅ {name:<30} -> OPERATIONAL")
                return True
            else:
                try:
                    error_msg = res.json().get("msg", "Unknown Error")
                except:
                    error_msg = f"HTML Response Error Flag (Status Code: {res.status_code})"
                print(f"❌ {name:<30} -> FAILED ({error_msg})")
                return False
        except Exception as err:
            print(f"❌ {name:<30} -> UNREACHABLE ({err})")
            return False

    functional = []
    broken = []

    if test_endpoint("Unified Balance Read", "GET", "/papi/v1/balance"):
        functional.append("Unified Balance Read")
    else:
        broken.append("Unified Balance Read")

    if test_endpoint("Account Information State", "GET", "/papi/v1/account"):
        functional.append("Account Information State")
    else:
        broken.append("Account Information State")

    if test_endpoint("USD-M Position Risk Sync", "GET", "/papi/v1/um/positionRisk"):
        functional.append("USD-M Position Risk Sync")
    else:
        broken.append("USD-M Position Risk Sync")

    order_payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "type": "LIMIT",
        "quantity": "0.01",
        "price": "30000",
        "timeInForce": "GTC",
        "newOrderRespType": "ACK",
        "test": "true"
    }
    if test_endpoint("Futures Order Verification", "POST", "/papi/v1/um/order", order_payload):
        functional.append("Futures Order Verification")
    else:
        broken.append("Futures Order Verification")

    print("\n====================================================")
    print("                  MATRIX SUMMARY                    ")
    print("====================================================")
    print(f"Operational Components ({len(functional)}): {', '.join(functional) if functional else 'None'}")
    print(f"Degraded Components    ({len(broken)}): {', '.join(broken) if broken else 'None'}")
    print("====================================================")

if __name__ == "__main__":
    run_comprehensive_matrix()
