"""
Analysis Engine — Computes 8 technical indicators and generates composite trade signals.

All indicator functions accept a list of OHLCV candle dicts and return a signal
score from -1.0 (strong sell) to +1.0 (strong buy), plus metadata.
"""

import numpy as np


# ---------------------------------------------------------------------------
# Helper: Extract arrays from candle list
# ---------------------------------------------------------------------------

def _extract(candles, key):
    """Extract a numpy array of a specific field from candle dicts."""
    return np.array([float(c[key]) for c in candles], dtype=np.float64)


def _ema(data, period):
    """Compute Exponential Moving Average."""
    if len(data) < period:
        return np.full_like(data, np.nan)
    ema = np.zeros_like(data)
    k = 2.0 / (period + 1)
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = data[i] * k + ema[i - 1] * (1 - k)
    return ema


def _sma(data, period):
    """Compute Simple Moving Average."""
    result = np.full_like(data, np.nan)
    for i in range(period - 1, len(data)):
        result[i] = np.mean(data[i - period + 1: i + 1])
    return result


def _true_range(high, low, close):
    """Compute True Range."""
    tr = np.zeros(len(high))
    tr[0] = high[0] - low[0]
    for i in range(1, len(high)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )
    return tr


# ---------------------------------------------------------------------------
# Indicator 1: MACD (12, 26, 9)
# ---------------------------------------------------------------------------

def compute_macd(candles):
    """
    MACD = EMA(12) - EMA(26), Signal = EMA(9) of MACD
    Bullish: MACD crosses above signal, histogram positive and growing
    Bearish: MACD crosses below signal, histogram negative and falling
    """
    close = _extract(candles, "close")
    if len(close) < 26:
        return {"signal": 0, "name": "MACD", "status": "Insufficient data", "details": {}}

    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd_line = ema12 - ema26
    signal_line = _ema(macd_line, 9)
    histogram = macd_line - signal_line

    # Current values
    curr_macd = macd_line[-1]
    curr_signal = signal_line[-1]
    curr_hist = histogram[-1]
    prev_hist = histogram[-2] if len(histogram) >= 2 else 0

    # Score: based on crossover + histogram momentum
    score = 0.0
    status = "Neutral"

    if curr_macd > curr_signal:
        score += 0.4
        status = "Bullish crossover"
    else:
        score -= 0.4
        status = "Bearish crossover"

    # Histogram direction
    if curr_hist > prev_hist:
        score += 0.3
        status += " + momentum increasing"
    else:
        score -= 0.3
        status += " + momentum decreasing"

    # Histogram magnitude relative to price
    hist_pct = abs(curr_hist) / close[-1] * 100
    if hist_pct > 0.5:
        magnitude_boost = min(0.3, hist_pct / 5)
        score += magnitude_boost if curr_hist > 0 else -magnitude_boost

    score = max(-1.0, min(1.0, score))

    return {
        "signal": round(score, 3),
        "name": "MACD (12,26,9)",
        "status": status,
        "details": {
            "macd": round(float(curr_macd), 4),
            "signal_line": round(float(curr_signal), 4),
            "histogram": round(float(curr_hist), 4),
        }
    }


# ---------------------------------------------------------------------------
# Indicator 2: RSI (14)
# ---------------------------------------------------------------------------

def compute_rsi(candles, period=14):
    """
    RSI = 100 - (100 / (1 + RS)), RS = avg_gain / avg_loss
    <30: Oversold (buy signal), >70: Overbought (sell signal)
    """
    close = _extract(candles, "close")
    if len(close) < period + 1:
        return {"signal": 0, "name": "RSI", "status": "Insufficient data", "details": {}}

    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # Wilder's smoothing (EMA-style)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

    # Score
    score = 0.0
    status = "Neutral"

    if rsi < 20:
        score = 0.9
        status = "Extremely oversold — strong buy"
    elif rsi < 30:
        score = 0.6
        status = "Oversold — buy signal"
    elif rsi < 40:
        score = 0.2
        status = "Mildly oversold"
    elif rsi > 80:
        score = -0.9
        status = "Extremely overbought — strong sell"
    elif rsi > 70:
        score = -0.6
        status = "Overbought — sell signal"
    elif rsi > 60:
        score = -0.2
        status = "Mildly overbought"
    else:
        score = 0.0
        status = "Neutral zone"

    return {
        "signal": round(score, 3),
        "name": f"RSI ({period})",
        "status": status,
        "details": {
            "rsi": round(float(rsi), 2),
        }
    }


# ---------------------------------------------------------------------------
# Indicator 3: Stochastic Oscillator (14, 3, 3)
# ---------------------------------------------------------------------------

def compute_stochastic(candles, k_period=14, d_period=3, smooth=3):
    """
    %K = (Close - Low14) / (High14 - Low14) * 100
    %D = SMA(%K, 3)
    <20: Oversold, >80: Overbought, crossover signals
    """
    close = _extract(candles, "close")
    high = _extract(candles, "high")
    low = _extract(candles, "low")

    if len(close) < k_period + d_period:
        return {"signal": 0, "name": "Stochastic", "status": "Insufficient data", "details": {}}

    # Raw %K
    raw_k = np.zeros(len(close))
    for i in range(k_period - 1, len(close)):
        highest = np.max(high[i - k_period + 1: i + 1])
        lowest = np.min(low[i - k_period + 1: i + 1])
        if highest == lowest:
            raw_k[i] = 50
        else:
            raw_k[i] = (close[i] - lowest) / (highest - lowest) * 100

    # Smooth %K
    smooth_k = _sma(raw_k, smooth)
    # %D
    pct_d = _sma(smooth_k, d_period)

    curr_k = smooth_k[-1]
    curr_d = pct_d[-1]
    prev_k = smooth_k[-2] if len(smooth_k) >= 2 else curr_k
    prev_d = pct_d[-2] if len(pct_d) >= 2 else curr_d

    if np.isnan(curr_k) or np.isnan(curr_d):
        return {"signal": 0, "name": "Stochastic", "status": "Insufficient data", "details": {}}

    score = 0.0
    status = "Neutral"

    # Zone scoring
    if curr_k < 20:
        score += 0.4
        status = "Oversold zone"
    elif curr_k > 80:
        score -= 0.4
        status = "Overbought zone"

    # Crossover scoring
    if prev_k <= prev_d and curr_k > curr_d:
        score += 0.5
        status += " + bullish crossover"
    elif prev_k >= prev_d and curr_k < curr_d:
        score -= 0.5
        status += " + bearish crossover"

    score = max(-1.0, min(1.0, score))

    return {
        "signal": round(score, 3),
        "name": f"Stochastic ({k_period},{d_period},{smooth})",
        "status": status,
        "details": {
            "percent_k": round(float(curr_k), 2),
            "percent_d": round(float(curr_d), 2),
        }
    }


# ---------------------------------------------------------------------------
# Indicator 4: Bollinger Bands (20, 2)
# ---------------------------------------------------------------------------

def compute_bollinger_bands(candles, period=20, std_mult=2):
    """
    Middle = SMA(20), Upper = Middle + 2*StdDev, Lower = Middle - 2*StdDev
    Price near lower band = buy, near upper band = sell
    Band squeeze = breakout imminent
    """
    close = _extract(candles, "close")
    if len(close) < period:
        return {"signal": 0, "name": "Bollinger Bands", "status": "Insufficient data", "details": {}}

    sma = _sma(close, period)
    rolling_std = np.full_like(close, np.nan)
    for i in range(period - 1, len(close)):
        rolling_std[i] = np.std(close[i - period + 1: i + 1])

    upper = sma + std_mult * rolling_std
    lower = sma - std_mult * rolling_std

    curr_close = close[-1]
    curr_upper = upper[-1]
    curr_lower = lower[-1]
    curr_middle = sma[-1]

    if np.isnan(curr_upper):
        return {"signal": 0, "name": "Bollinger Bands", "status": "Insufficient data", "details": {}}

    band_width = curr_upper - curr_lower
    position = (curr_close - curr_lower) / band_width if band_width > 0 else 0.5

    # Bandwidth relative to price (squeeze detection)
    bw_pct = band_width / curr_middle * 100

    score = 0.0
    status = "Neutral"

    if position < 0.1:
        score = 0.7
        status = "Price at/below lower band — oversold bounce likely"
    elif position < 0.25:
        score = 0.4
        status = "Price near lower band — potential support"
    elif position > 0.9:
        score = -0.7
        status = "Price at/above upper band — overbought"
    elif position > 0.75:
        score = -0.4
        status = "Price near upper band — potential resistance"
    else:
        status = "Price within normal range"

    # Squeeze detection
    if bw_pct < 2:
        status += " | Band squeeze — breakout imminent"

    return {
        "signal": round(score, 3),
        "name": f"Bollinger Bands ({period},{std_mult})",
        "status": status,
        "details": {
            "upper": round(float(curr_upper), 2),
            "middle": round(float(curr_middle), 2),
            "lower": round(float(curr_lower), 2),
            "bandwidth_pct": round(float(bw_pct), 3),
            "position": round(float(position), 3),
        }
    }


# ---------------------------------------------------------------------------
# Indicator 5: EMA Crossover (9/21 fast, 50/200 slow)
# ---------------------------------------------------------------------------

def compute_ema_crossover(candles):
    """
    Fast cross: EMA9 vs EMA21 — short-term trend
    Slow cross: EMA50 vs EMA200 — golden/death cross
    """
    close = _extract(candles, "close")
    results = {}

    score = 0.0
    status_parts = []

    # Fast crossover (9/21)
    if len(close) >= 21:
        ema9 = _ema(close, 9)
        ema21 = _ema(close, 21)

        if ema9[-1] > ema21[-1]:
            score += 0.3
            status_parts.append("EMA9 > EMA21 (short-term bullish)")
        else:
            score -= 0.3
            status_parts.append("EMA9 < EMA21 (short-term bearish)")

        results["ema9"] = round(float(ema9[-1]), 2)
        results["ema21"] = round(float(ema21[-1]), 2)

    # Slow crossover (50/200)
    if len(close) >= 200:
        ema50 = _ema(close, 50)
        ema200 = _ema(close, 200)

        if ema50[-1] > ema200[-1]:
            score += 0.4
            status_parts.append("Golden cross (EMA50 > EMA200)")
        else:
            score -= 0.4
            status_parts.append("Death cross (EMA50 < EMA200)")

        results["ema50"] = round(float(ema50[-1]), 2)
        results["ema200"] = round(float(ema200[-1]), 2)
    elif len(close) >= 50:
        ema50 = _ema(close, 50)
        results["ema50"] = round(float(ema50[-1]), 2)
        # Price vs EMA50
        if close[-1] > ema50[-1]:
            score += 0.2
            status_parts.append("Price above EMA50")
        else:
            score -= 0.2
            status_parts.append("Price below EMA50")

    score = max(-1.0, min(1.0, score))
    status = " | ".join(status_parts) if status_parts else "Insufficient data"

    return {
        "signal": round(score, 3),
        "name": "EMA Crossover (9/21 + 50/200)",
        "status": status,
        "details": results,
    }


# ---------------------------------------------------------------------------
# Indicator 6: ADX (14) — Average Directional Index
# ---------------------------------------------------------------------------

def compute_adx(candles, period=14):
    """
    ADX measures trend strength. >25 = trending, <20 = ranging.
    Combined with +DI/-DI for direction.
    """
    high = _extract(candles, "high")
    low = _extract(candles, "low")
    close = _extract(candles, "close")

    if len(close) < period * 2:
        return {"signal": 0, "name": "ADX", "status": "Insufficient data", "details": {}}

    # Compute +DM and -DM
    plus_dm = np.zeros(len(high))
    minus_dm = np.zeros(len(high))
    tr = _true_range(high, low, close)

    for i in range(1, len(high)):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]

        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    # Smooth with Wilder's method
    atr = np.zeros(len(tr))
    smooth_plus = np.zeros(len(tr))
    smooth_minus = np.zeros(len(tr))

    atr[period] = np.mean(tr[1:period + 1])
    smooth_plus[period] = np.mean(plus_dm[1:period + 1])
    smooth_minus[period] = np.mean(minus_dm[1:period + 1])

    for i in range(period + 1, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        smooth_plus[i] = (smooth_plus[i - 1] * (period - 1) + plus_dm[i]) / period
        smooth_minus[i] = (smooth_minus[i - 1] * (period - 1) + minus_dm[i]) / period

    # +DI and -DI
    plus_di = np.zeros(len(tr))
    minus_di = np.zeros(len(tr))
    dx = np.zeros(len(tr))

    for i in range(period, len(tr)):
        if atr[i] > 0:
            plus_di[i] = (smooth_plus[i] / atr[i]) * 100
            minus_di[i] = (smooth_minus[i] / atr[i]) * 100

        di_sum = plus_di[i] + minus_di[i]
        if di_sum > 0:
            dx[i] = abs(plus_di[i] - minus_di[i]) / di_sum * 100

    # ADX = smoothed DX
    adx_vals = np.zeros(len(tr))
    start = period * 2
    if start < len(dx):
        adx_vals[start] = np.mean(dx[period + 1:start + 1])
        for i in range(start + 1, len(dx)):
            adx_vals[i] = (adx_vals[i - 1] * (period - 1) + dx[i]) / period

    curr_adx = adx_vals[-1]
    curr_plus_di = plus_di[-1]
    curr_minus_di = minus_di[-1]
    curr_atr = atr[-1]

    score = 0.0
    status = ""

    # Direction from DI
    if curr_plus_di > curr_minus_di:
        direction = 0.5
        status = "Bullish trend"
    else:
        direction = -0.5
        status = "Bearish trend"

    # Strength scaling
    if curr_adx > 40:
        score = direction * 1.0
        status += f" — Very strong (ADX={curr_adx:.1f})"
    elif curr_adx > 25:
        score = direction * 0.7
        status += f" — Strong (ADX={curr_adx:.1f})"
    elif curr_adx > 20:
        score = direction * 0.3
        status += f" — Weak trend (ADX={curr_adx:.1f})"
    else:
        score = 0.0
        status = f"No clear trend — ranging market (ADX={curr_adx:.1f})"

    score = max(-1.0, min(1.0, score))

    return {
        "signal": round(score, 3),
        "name": f"ADX ({period})",
        "status": status,
        "details": {
            "adx": round(float(curr_adx), 2),
            "plus_di": round(float(curr_plus_di), 2),
            "minus_di": round(float(curr_minus_di), 2),
            "atr": round(float(curr_atr), 2),
        }
    }


# ---------------------------------------------------------------------------
# Indicator 7: Ichimoku Cloud
# ---------------------------------------------------------------------------

def compute_ichimoku(candles):
    """
    Tenkan-sen (9), Kijun-sen (26), Senkou Span A/B, Chikou Span.
    Price above cloud = bullish, below = bearish.
    Tenkan > Kijun = bullish crossover.
    """
    high = _extract(candles, "high")
    low = _extract(candles, "low")
    close = _extract(candles, "close")

    if len(close) < 52:
        return {"signal": 0, "name": "Ichimoku Cloud", "status": "Insufficient data (need 52+ candles)", "details": {}}

    def donchian_mid(h, l, period, idx):
        s = max(0, idx - period + 1)
        return (np.max(h[s:idx + 1]) + np.min(l[s:idx + 1])) / 2

    n = len(close)
    tenkan = donchian_mid(high, low, 9, n - 1)
    kijun = donchian_mid(high, low, 26, n - 1)
    senkou_a = (tenkan + kijun) / 2
    senkou_b = donchian_mid(high, low, 52, n - 1)

    curr_price = close[-1]
    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)

    score = 0.0
    status_parts = []

    # Price vs cloud
    if curr_price > cloud_top:
        score += 0.4
        status_parts.append("Price above cloud (bullish)")
    elif curr_price < cloud_bottom:
        score -= 0.4
        status_parts.append("Price below cloud (bearish)")
    else:
        status_parts.append("Price inside cloud (indecision)")

    # Tenkan vs Kijun
    if tenkan > kijun:
        score += 0.3
        status_parts.append("Tenkan > Kijun (bullish)")
    else:
        score -= 0.3
        status_parts.append("Tenkan < Kijun (bearish)")

    # Cloud color (future sentiment)
    if senkou_a > senkou_b:
        score += 0.2
        status_parts.append("Green cloud ahead")
    else:
        score -= 0.2
        status_parts.append("Red cloud ahead")

    score = max(-1.0, min(1.0, score))

    return {
        "signal": round(score, 3),
        "name": "Ichimoku Cloud",
        "status": " | ".join(status_parts),
        "details": {
            "tenkan_sen": round(float(tenkan), 2),
            "kijun_sen": round(float(kijun), 2),
            "senkou_a": round(float(senkou_a), 2),
            "senkou_b": round(float(senkou_b), 2),
            "cloud_top": round(float(cloud_top), 2),
            "cloud_bottom": round(float(cloud_bottom), 2),
        }
    }


# ---------------------------------------------------------------------------
# Indicator 8: VWAP (Volume Weighted Average Price)
# ---------------------------------------------------------------------------

def compute_vwap(candles):
    """
    VWAP = cumulative(TypicalPrice * Volume) / cumulative(Volume)
    Price above VWAP = bullish, below = bearish
    """
    close = _extract(candles, "close")
    high = _extract(candles, "high")
    low = _extract(candles, "low")
    volume = _extract(candles, "volume")

    if len(close) < 10:
        return {"signal": 0, "name": "VWAP", "status": "Insufficient data", "details": {}}

    typical_price = (high + low + close) / 3
    cum_tp_vol = np.cumsum(typical_price * volume)
    cum_vol = np.cumsum(volume)

    # Avoid division by zero
    vwap = np.where(cum_vol > 0, cum_tp_vol / cum_vol, typical_price)

    curr_vwap = vwap[-1]
    curr_price = close[-1]
    deviation_pct = (curr_price - curr_vwap) / curr_vwap * 100

    score = 0.0
    status = ""

    if deviation_pct > 1.5:
        score = -0.5
        status = f"Price {deviation_pct:.2f}% above VWAP — extended"
    elif deviation_pct > 0.3:
        score = 0.3
        status = f"Price above VWAP — bullish"
    elif deviation_pct < -1.5:
        score = 0.5
        status = f"Price {abs(deviation_pct):.2f}% below VWAP — discount"
    elif deviation_pct < -0.3:
        score = -0.3
        status = f"Price below VWAP — bearish"
    else:
        score = 0.0
        status = "Price at VWAP — neutral"

    return {
        "signal": round(score, 3),
        "name": "VWAP",
        "status": status,
        "details": {
            "vwap": round(float(curr_vwap), 2),
            "deviation_pct": round(float(deviation_pct), 3),
        }
    }


# ---------------------------------------------------------------------------
# Composite Signal Generator
# ---------------------------------------------------------------------------

# Weights for the composite signal (sum = 1.0)
INDICATOR_WEIGHTS = {
    "MACD": 0.15,
    "RSI": 0.15,
    "Stochastic": 0.10,
    "Bollinger": 0.10,
    "EMA": 0.15,
    "ADX": 0.15,
    "Ichimoku": 0.10,
    "VWAP": 0.10,
}


def analyze(candles, timeframe="5m", baselines=None):
    """
    Run all indicators on the given candle data and produce a composite signal.

    Args:
        candles: List of dicts with keys: open, high, low, close, volume
        timeframe: User's chart timeframe string
        baselines: Pre-computed baselines from data_preprocessor (optional)

    Returns:
        dict with composite signal, individual indicators, trade recommendation
    """
    if not candles or len(candles) < 10:
        return {
            "error": "Need at least 10 candles for analysis. Provide 50+ for best results.",
            "direction": "HOLD",
            "confidence": 0,
        }

    # Run all indicators
    indicators = []
    indicator_funcs = [
        ("MACD", compute_macd),
        ("RSI", compute_rsi),
        ("Stochastic", compute_stochastic),
        ("Bollinger", compute_bollinger_bands),
        ("EMA", compute_ema_crossover),
        ("ADX", compute_adx),
        ("Ichimoku", compute_ichimoku),
        ("VWAP", compute_vwap),
    ]

    weighted_sum = 0.0
    total_weight = 0.0

    for key, func in indicator_funcs:
        result = func(candles)
        weight = INDICATOR_WEIGHTS[key]

        if result["signal"] != 0 or result.get("status") != "Insufficient data":
            weighted_sum += result["signal"] * weight
            total_weight += weight

        indicators.append(result)

    # Composite score
    if total_weight > 0:
        composite = weighted_sum / total_weight
    else:
        composite = 0.0

    # Direction
    if composite > 0.15:
        direction = "LONG"
    elif composite < -0.15:
        direction = "SHORT"
    else:
        direction = "HOLD"

    # Confidence (0–100%)
    confidence = min(100, int(abs(composite) * 100 / 0.7 * 100) // 100)
    confidence = min(95, max(5, int(abs(composite) / 1.0 * 100)))

    # Recommended timeframe for trade
    recommended_tf = _recommend_timeframe(composite, indicators, timeframe)

    # Support/resistance from baselines
    sr_levels = []
    if baselines and "support_resistance" in baselines:
        sr_levels = baselines["support_resistance"]

    # ATR-based stop/target from ADX indicator
    atr = 0
    for ind in indicators:
        if "atr" in ind.get("details", {}):
            atr = ind["details"]["atr"]
            break

    current_price = float(candles[-1]["close"])

    trade_plan = {}
    if direction == "LONG":
        trade_plan = {
            "entry_zone": f"${current_price:,.2f}",
            "stop_loss": f"${current_price - atr * 1.5:,.2f}" if atr else "N/A",
            "take_profit_1": f"${current_price + atr * 2:,.2f}" if atr else "N/A",
            "take_profit_2": f"${current_price + atr * 3:,.2f}" if atr else "N/A",
            "risk_reward": "1:2 to 1:3",
        }
    elif direction == "SHORT":
        trade_plan = {
            "entry_zone": f"${current_price:,.2f}",
            "stop_loss": f"${current_price + atr * 1.5:,.2f}" if atr else "N/A",
            "take_profit_1": f"${current_price - atr * 2:,.2f}" if atr else "N/A",
            "take_profit_2": f"${current_price - atr * 3:,.2f}" if atr else "N/A",
            "risk_reward": "1:2 to 1:3",
        }

    return {
        "direction": direction,
        "composite_score": round(composite, 4),
        "confidence": confidence,
        "recommended_timeframe": recommended_tf,
        "indicators": indicators,
        "trade_plan": trade_plan,
        "current_price": current_price,
        "support_resistance": sr_levels[:6],
        "candles_analyzed": len(candles),
        "input_timeframe": timeframe,
    }


def _recommend_timeframe(composite, indicators, input_tf):
    """
    Based on signal strength and ADX, recommend a candle timeframe.
    Strong trends → longer timeframes, weak trends → shorter scalps.
    """
    adx_val = 0
    for ind in indicators:
        if "adx" in ind.get("details", {}):
            adx_val = ind["details"]["adx"]

    strength = abs(composite)

    if adx_val > 30 and strength > 0.5:
        return {
            "timeframe": "1h - 4h",
            "reason": "Strong trend detected — longer timeframe for swing trade",
            "hold_duration": "4-24 hours",
        }
    elif adx_val > 25 and strength > 0.3:
        return {
            "timeframe": "15m - 1h",
            "reason": "Moderate trend — medium timeframe",
            "hold_duration": "1-4 hours",
        }
    elif strength > 0.2:
        return {
            "timeframe": "5m - 15m",
            "reason": "Weak signal — shorter timeframe for quick scalp",
            "hold_duration": "15-60 minutes",
        }
    else:
        return {
            "timeframe": "N/A",
            "reason": "Signal too weak — wait for clearer setup",
            "hold_duration": "Do not trade",
        }
