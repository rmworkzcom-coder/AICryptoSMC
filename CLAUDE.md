# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
AICryptoSMC is an automated trading bot and dashboard system that utilizes **Smart Money Concepts (SMC)** to identify market structures and execute trades on cryptocurrency markets (e.g., Binance).

### Architecture
- **Backend (`backend/`)**: A Python FastAPI server managing the core logic:
    - `smc_engine.py`: The core engine for identifying Break of Structure (BOS), Change of Character (CHoCH), and liquidity sweeps.
    - `live_trader.py`: Handles real-time order execution, balance management, and active trade states.
    - `backtester.py`: Executes simulations on historical data to validate strategies.
    - `api.py`: Exposes endpoints for charts, bot status, configurations, and trading history.
    - `constants.py`: Central configuration constants.
- **Frontend (`frontend/`)**: A React application built with Vite:
    - **Dashboard**: Real-time monitoring of active positions, scan progress, and connection status.
    - **Real-time Charting**: Interactive visualization of SMC structures using `lightweight-charts`.
    - **History Analysis**: Detailed breakdown of completed trades, including Win Rate and Profit Factor metrics.

## Development Commands

### Run Development Servers
- **Backend Server**: `python backend/main.py` (Runs on port 8005)
- **Frontend Dashboard**: `npm run dev` (Runs on port 3009)

### Building & Linting
- **Build Frontend**: `npm run build`
- **Lint Frontend**: `npm run lint`

## Key Context & Logic
- **Real-time updates**: The system uses WebSockets for real-time status broadcasts and interaction logs.
- **Trading Modes**: Supports both 'live' (connecting to Binance) and 'paper' (simulated) trading modes via the internal configuration.
- **SMC Calculations**: Core calculations are performed in `smc_engine.py` using pandas/numpy for efficiency.
