"""
Data Preprocessor — Extracts statistical baselines from the BTC/USD CSV dataset.

Loads the last ~2 years of 1-minute candle data and computes:
  - Support/resistance zones via price clustering
  - Volatility percentiles
  - Historical price regime statistics
"""

import os
import json
import time
import numpy as np
import pandas as pd

CSV_PATH = os.path.join(os.path.dirname(__file__), "btcusd_1-min_data.csv")
CACHE_PATH = os.path.join(os.path.dirname(__file__), "baselines_cache.json")

# Only load the last N rows to keep memory reasonable (~2 years of 1-min data)
TAIL_ROWS = 1_050_000  # ~2 years of 1-min candles


def _load_recent_data():
    """Load the tail of the CSV efficiently by reading file lines from the end."""
    import io

    print("[Preprocessor] Reading tail of CSV file...")

    # Read the last TAIL_ROWS lines efficiently
    lines = []
    header = None
    with open(CSV_PATH, "r") as f:
        header = f.readline().strip()  # Read header
        # Read all remaining lines (we'll keep only the tail)
        for line in f:
            lines.append(line)

    total_lines = len(lines)
    tail_lines = lines[-TAIL_ROWS:] if total_lines > TAIL_ROWS else lines
    print(f"[Preprocessor] Total data rows: {total_lines:,}. Loading last {len(tail_lines):,}...")

    # Reconstruct CSV text with header
    csv_text = header + "\n" + "".join(tail_lines)
    del lines, tail_lines  # Free memory

    df = pd.read_csv(
        io.StringIO(csv_text),
        dtype={"Timestamp": np.int64, "Open": np.float64, "High": np.float64,
               "Low": np.float64, "Close": np.float64, "Volume": np.float64},
    )
    del csv_text  # Free memory

    # Drop rows with zero volume and identical OHLC (stale/empty candles)
    df = df[
        (df["Volume"] > 0) |
        (df["Open"] != df["Close"]) |
        (df["High"] != df["Low"])
    ].copy()

    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)
    print(f"[Preprocessor] Loaded {len(df):,} active candles.")
    return df


def _compute_support_resistance(df, num_levels=8):
    """
    Identify support/resistance levels using price density clustering.
    Groups prices into bins and finds the most frequently visited price zones.
    """
    closes = df["Close"].values
    price_min, price_max = closes.min(), closes.max()
    num_bins = 200
    hist, bin_edges = np.histogram(closes, bins=num_bins)

    # Find peaks in the histogram (local maxima)
    levels = []
    for i in range(1, len(hist) - 1):
        if hist[i] > hist[i - 1] and hist[i] > hist[i + 1] and hist[i] > np.percentile(hist, 75):
            price_level = (bin_edges[i] + bin_edges[i + 1]) / 2
            levels.append({"price": round(float(price_level), 2), "strength": int(hist[i])})

    # Sort by strength and take top N
    levels.sort(key=lambda x: x["strength"], reverse=True)
    return levels[:num_levels]


def _compute_volatility_profile(df):
    """Compute volatility percentiles from historical data."""
    # Calculate 1-minute returns
    returns = df["Close"].pct_change().dropna()

    # Rolling 60-candle (1 hour) standard deviation
    rolling_vol = returns.rolling(60).std().dropna()

    percentiles = {}
    for p in [10, 25, 50, 75, 90, 95]:
        percentiles[f"p{p}"] = round(float(np.percentile(rolling_vol, p)), 8)

    return {
        "return_std": round(float(returns.std()), 8),
        "return_mean": round(float(returns.mean()), 8),
        "hourly_vol_percentiles": percentiles,
    }


def _compute_regime_stats(df):
    """Compute statistics per price regime."""
    regimes = [
        {"name": "below_10k", "min": 0, "max": 10000},
        {"name": "10k_30k", "min": 10000, "max": 30000},
        {"name": "30k_60k", "min": 30000, "max": 60000},
        {"name": "60k_100k", "min": 60000, "max": 100000},
        {"name": "above_100k", "min": 100000, "max": float("inf")},
    ]

    stats = {}
    for regime in regimes:
        mask = (df["Close"] >= regime["min"]) & (df["Close"] < regime["max"])
        subset = df[mask]
        if len(subset) < 100:
            continue

        returns = subset["Close"].pct_change().dropna()
        stats[regime["name"]] = {
            "candle_count": int(len(subset)),
            "avg_close": round(float(subset["Close"].mean()), 2),
            "avg_volume": round(float(subset["Volume"].mean()), 6),
            "return_std": round(float(returns.std()), 8),
            "avg_range_pct": round(float(((subset["High"] - subset["Low"]) / subset["Close"]).mean() * 100), 4),
        }

    return stats


def _compute_recent_context(df):
    """Get the most recent price context for the analysis engine."""
    last_row = df.iloc[-1]
    last_1000 = df.tail(1000)

    # Simple moving averages on the last chunk
    closes = last_1000["Close"].values
    sma_50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else float(closes[-1])
    sma_200 = float(np.mean(closes[-200:])) if len(closes) >= 200 else float(closes[-1])

    return {
        "last_price": round(float(last_row["Close"]), 2),
        "last_timestamp": int(last_row["Timestamp"]),
        "sma_50": round(sma_50, 2),
        "sma_200": round(sma_200, 2),
        "trend_bias": "bullish" if sma_50 > sma_200 else "bearish",
        "data_end_date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(last_row["Timestamp"])),
    }


def build_baselines(force=False):
    """
    Build and cache all baselines. Returns the baselines dict.
    If a cache exists and force=False, loads from cache.
    """
    if not force and os.path.exists(CACHE_PATH):
        print("[Preprocessor] Loading cached baselines...")
        with open(CACHE_PATH, "r") as f:
            return json.load(f)

    print("[Preprocessor] Building baselines from CSV (this takes 1-3 minutes)...")
    start = time.time()
    df = _load_recent_data()

    baselines = {
        "support_resistance": _compute_support_resistance(df),
        "volatility_profile": _compute_volatility_profile(df),
        "regime_stats": _compute_regime_stats(df),
        "recent_context": _compute_recent_context(df),
        "computed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }

    # Cache to disk
    with open(CACHE_PATH, "w") as f:
        json.dump(baselines, f, indent=2)

    elapsed = time.time() - start
    print(f"[Preprocessor] Baselines computed in {elapsed:.1f}s and cached.")
    return baselines


if __name__ == "__main__":
    baselines = build_baselines(force=True)
    print(json.dumps(baselines, indent=2))
