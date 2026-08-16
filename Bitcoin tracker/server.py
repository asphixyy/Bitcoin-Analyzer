"""
Flask API Server for Bitcoin Chart Analyzer.

Endpoints:
  GET  /                    — Serve the frontend
  POST /api/analyze         — Analyze OHLCV candle data
  GET  /api/fetch-live      — Fetch live candles from Binance
  GET  /api/fetch-and-analyze — Fetch live + analyze in one call
  GET  /api/baselines       — Return pre-computed baselines
  GET  /api/health          — Health check
"""

import os
import json
import traceback
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from analysis_engine import analyze
from data_preprocessor import build_baselines
from live_data import fetch_live_candles

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# Build baselines on startup (uses cache if available)
print("=" * 60)
print("  Bitcoin Chart Analyzer — Starting up...")
print("=" * 60)

try:
    BASELINES = build_baselines(force=False)
    print("[Server] Baselines loaded successfully.")
except Exception as e:
    print(f"[Server] WARNING: Could not load baselines: {e}")
    print("[Server] The analyzer will still work, but without historical context.")
    BASELINES = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main HTML page."""
    return send_from_directory(".", "index.html")


@app.route("/styles.css")
def styles():
    return send_from_directory(".", "styles.css")


@app.route("/app.js")
def appjs():
    return send_from_directory(".", "app.js")


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "baselines_loaded": bool(BASELINES),
        "service": "Bitcoin Chart Analyzer",
    })


@app.route("/api/baselines")
def get_baselines():
    """Return the pre-computed baselines."""
    return jsonify(BASELINES)


@app.route("/api/fetch-live")
def fetch_live():
    """
    Fetch live OHLCV candles from Binance.
    Query params:
      - timeframe: 1m, 5m, 15m, 1h, 4h (default: 5m)
      - limit: number of candles 10-1000 (default: 100)
    """
    timeframe = request.args.get("timeframe", "5m")
    limit = request.args.get("limit", "100")

    try:
        limit = max(10, min(1000, int(limit)))
    except ValueError:
        limit = 100

    result = fetch_live_candles(timeframe=timeframe, limit=limit)

    if not result.get("success"):
        return jsonify(result), 502

    return jsonify(result)


@app.route("/api/fetch-and-analyze")
def fetch_and_analyze():
    """
    Fetch live candles from Binance AND run analysis in one call.
    Query params:
      - timeframe: 1m, 5m, 15m, 1h, 4h (default: 5m)
      - limit: number of candles (default: 100)
    """
    timeframe = request.args.get("timeframe", "5m")
    limit = request.args.get("limit", "100")

    try:
        limit = max(10, min(1000, int(limit)))
    except ValueError:
        limit = 100

    # Step 1: Fetch live data
    live = fetch_live_candles(timeframe=timeframe, limit=limit)
    if not live.get("success"):
        return jsonify(live), 502

    # Step 2: Run analysis on fetched candles
    candles = live["candles"]
    analysis = analyze(candles, timeframe=timeframe, baselines=BASELINES)

    # Merge live metadata into analysis result
    analysis["live_data"] = {
        "symbol": live["symbol"],
        "fetched_at": live["fetched_at"],
        "ticker_24h": live.get("ticker_24h"),
    }

    return jsonify(analysis)


@app.route("/api/analyze", methods=["POST"])
def analyze_chart():
    """
    Analyze OHLCV candle data.

    Expects JSON body:
    {
        "candles": [
            {"open": 63000, "high": 63100, "low": 62900, "close": 63050, "volume": 1.5},
            ...
        ],
        "timeframe": "5m"
    }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "No JSON body provided"}), 400

        candles = data.get("candles", [])
        timeframe = data.get("timeframe", "5m")

        if not candles:
            return jsonify({"error": "No candle data provided. Send an array of {open, high, low, close, volume} objects."}), 400

        if len(candles) < 10:
            return jsonify({"error": f"Only {len(candles)} candles provided. Need at least 10, recommend 50+."}), 400

        # Validate candle structure
        required_keys = {"open", "high", "low", "close", "volume"}
        for i, candle in enumerate(candles):
            missing = required_keys - set(candle.keys())
            if missing:
                return jsonify({"error": f"Candle {i} missing keys: {missing}"}), 400
            # Coerce to float
            for k in required_keys:
                try:
                    candle[k] = float(candle[k])
                except (ValueError, TypeError):
                    return jsonify({"error": f"Candle {i} has non-numeric value for '{k}': {candle[k]}"}), 400

        # Run analysis
        result = analyze(candles, timeframe=timeframe, baselines=BASELINES)

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  Server running at http://localhost:5000")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
