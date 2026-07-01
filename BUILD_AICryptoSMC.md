# BUILD INSTRUCTIONS — AICryptoSMC

This document explains how to build, run, and verify the AICryptoSMC trading scanner (FastAPI backend + React frontend) from a clean checkout. Use this as the canonical "build" guide for the project.

Prerequisites
- macOS or Linux
- Python 3.10+
- Node.js 18+ and npm/yarn
- Git

Secrets
- Create `.env.local` in the repository root (next to `backend/`) containing:

```
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
# Optional for Portfolio Margin PAPI
PAPI_API_KEY=...
PAPI_API_SECRET=...
```

Backend: setup and run

1. Create Python virtualenv and install deps

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

2. Start the backend server

```bash
# From repository root
PYTHONPATH=. venv/bin/python backend/main.py
```

- Backend serves API at `http://127.0.0.1:8005` by default.
- Primary endpoints:
  - `GET /bot/status` — returns runtime state including `scanning`, `binance_auth_status` and `binance_last_success`.
  - `POST /bot/check-auth` — validate Binance credentials and PAPI fallback.
  - `GET|POST /config` — read/update runtime config (e.g., `adx_threshold`, `symbols`).

Frontend: setup and run

```bash
cd frontend
npm install
npm run dev
```

- Frontend runs at `http://127.0.0.1:3009` by default and connects to the backend websocket at `ws://127.0.0.1:8005/api/ws`.

Verifications

1. Confirm backend is reachable

```bash
curl http://127.0.0.1:8005/bot/status | jq .
```

2. Run auth check

```bash
curl -sS -X POST http://127.0.0.1:8005/bot/check-auth -H 'Content-Type: application/json' | jq .
```

Expected: `success: true` when valid keys present. The `binance_last_success` field is included in `/bot/status` and holds `(status, source, mode, ts)` for the most recent successful check.

Logs and evidence

- `backend/trader.log` — primary runtime evidence. Watch for lines like:
  - `ADX X < threshold Y. Skipping entry.`
  - `Bullish/Bearish sweep found at idx ...`
  - `OPENED` / `CLOSED` events
  - API errors or DNS resolution issues

Experiment harness (A/B sampling)

A minimal harness to compare baseline vs relaxed configs (lower ADX / pruned symbols):

```bash
# Save original config
curl -sS http://127.0.0.1:8005/config > /tmp/orig_cfg.json

# apply relaxed config (example)
python3 - <<'PY'
import json,urllib.request
orig=json.load(open('/tmp/orig_cfg.json'))
rel=dict(orig)
rel['adx_threshold']=4.0
rel['symbols']=['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','ADAUSDT','AVAXUSDT']
req=urllib.request.Request('http://127.0.0.1:8005/config', data=json.dumps(rel).encode('utf-8'), headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req) as r:
    print('Applied relaxed config', r.read().decode())
PY

# Wait for several scan cycles and inspect logs
sleep 3
# tail new lines of backend/trader.log and grep for metrics
```

Troubleshooting

- If `/bot/check-auth` shows failure but you expect success:
  - Verify `.env.local` is in repo root and contains non-placeholder keys.
  - Check `backend/trader.log` for errors about loading keys.
  - Re-run `POST /bot/check-auth` and inspect `binance_last_success` in `/bot/status`.

- If few trades open:
  - Inspect `backend/trader.log` for ADX rejections and structure gate messages.
  - Temporarily lower `adx_threshold` or enable `bypass_structure_check` via `/config` for controlled experiments.

Files of interest

- `backend/live_trader.py` — core scanning logic and Binance auth handling
- `backend/api.py` — state payload and endpoints consumed by the frontend
- `backend/config.json` — runtime config used by `/config` endpoint
- `backend/trades.json` — persistent trade state and freeze list
- `frontend/src/App.jsx` — UI rendering of auth and scanning state

Next recommended actions

- Update the frontend to prefer `binance_last_success` when in `paper` mode so dashboard reflects recent successful auth.
- Run a longer experiment (30+ scan cycles) capturing `backend/trader.log` slices for statistical analysis of opened vs rejected counts.

