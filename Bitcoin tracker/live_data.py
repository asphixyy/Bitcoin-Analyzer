"""
Live Data Fetcher — Pulls real-time OHLCV candle data from Binance public API.

No API key required. Uses the public klines endpoint:
  GET https://api.binance.com/api/v3/klines

Supported intervals: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w
"""

import time
import requests

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
SYMBOL = "BTCUSDT"

# Map user-friendly timeframe labels to Binance interval codes
TIMEFRAME_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
}


def fetch_live_candles(timeframe="5m", limit=100):
    """
    Fetch live OHLCV candles from Binance.

    Args:
        timeframe: Candle interval (1m, 5m, 15m, 1h, 4h, etc.)
        limit: Number of candles to fetch (max 1000)

    Returns:
        dict with candles list, current price, and metadata
    """
    interval = TIMEFRAME_MAP.get(timeframe, "5m")
    limit = min(limit, 1000)  # Binance max is 1000

    try:
        # Fetch klines (candlestick data)
        resp = requests.get(
            BINANCE_KLINES_URL,
            params={
                "symbol": SYMBOL,
                "interval": interval,
                "limit": limit,
            },
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.json()

        # Binance kline format:
        # [0] Open time, [1] Open, [2] High, [3] Low, [4] Close,
        # [5] Volume, [6] Close time, [7] Quote asset volume,
        # [8] Number of trades, [9] Taker buy base, [10] Taker buy quote, [11] Ignore
        candles = []
        for k in raw:
            candles.append({
                "timestamp": int(k[0]) // 1000,  # ms → seconds
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "trades": int(k[8]),
            })

        current_price = candles[-1]["close"] if candles else 0

        # Also fetch 24h ticker for context
        ticker = _fetch_24h_ticker()

        return {
            "success": True,
            "candles": candles,
            "current_price": current_price,
            "symbol": SYMBOL,
            "timeframe": timeframe,
            "candle_count": len(candles),
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "ticker_24h": ticker,
        }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Binance API timed out. Please try again."}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Cannot connect to Binance API. Check your internet connection."}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"Binance API error: {e.response.status_code} — {e.response.text[:200]}"}
    except Exception as e:
        return {"success": False, "error": f"Failed to fetch live data: {str(e)}"}


def _fetch_24h_ticker():
    """Fetch 24-hour price change statistics."""
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": SYMBOL},
            timeout=5,
        )
        resp.raise_for_status()
        t = resp.json()
        return {
            "price_change": float(t["priceChange"]),
            "price_change_pct": float(t["priceChangePercent"]),
            "high_24h": float(t["highPrice"]),
            "low_24h": float(t["lowPrice"]),
            "volume_24h": float(t["volume"]),
            "quote_volume_24h": float(t["quoteVolume"]),
        }
    except Exception:
        return None


if __name__ == "__main__":
    import json
    result = fetch_live_candles("5m", 20)
    print(json.dumps(result, indent=2))
