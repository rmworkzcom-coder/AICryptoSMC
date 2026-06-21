import uvicorn
import os

if __name__ == "__main__":
    # Ensure logs directory and files exist
    log_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.join(log_dir, "trader.log")
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("")

    # Run FastAPI server
    uvicorn.run("backend.api:app", host="0.0.0.0", port=8000, reload=True)
