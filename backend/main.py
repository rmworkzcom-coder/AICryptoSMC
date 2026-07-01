import os
import sys
import uvicorn

# Ensure backend package is importable when running main.py directly
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

if __name__ == "__main__":
    # Ensure logs directory and files exist
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(log_dir, "trader.log")
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("")

    # Run FastAPI server without auto-reload for stable WebSocket connections
    uvicorn.run("backend.api:app", host="0.0.0.0", port=8005, reload=False)
