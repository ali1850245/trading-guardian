"""Runtime extensions kept separate from the core engine to make upgrades reviewable."""
from __future__ import annotations

import engine


# The public APIs used by the core engine do not natively provide 2-day candles.
# Build them from closed daily candles instead of pretending an unsupported API interval exists.
_original_get_candles = engine.get_candles


def get_candles(symbol=engine.DEFAULT_SYMBOL, resolution="15", limit=300):
    if str(resolution) != "2D":
        return _original_get_candles(symbol, resolution, limit)
    daily = _original_get_candles(symbol, "1D", max(limit * 2 + 4, engine.MIN_CANDLES))
    if len(daily) < 2:
        raise RuntimeError("Not enough daily candles for 2d aggregation")
    frame = daily.copy().reset_index(drop=True)
    frame["group"] = frame.index // 2
    out = frame.groupby("group", sort=True).agg(
        timestamp=("timestamp", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index(drop=True)
    return out.tail(limit).reset_index(drop=True)


def timeframe_analysis(df):
    base = engine.timeframe_analysis(df)
    x = df.iloc[-1]
    close = float(x["close"])
    volume = float(x.get("volume", 0) or 0)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    volsum = df["volume"].rolling(20).sum().iloc[-1] if "volume" in df else 0
    vwap = float((typical * df["volume"]).rolling(20).sum().iloc[-1] / volsum) if volsum else close
    hh = float(df["high"].rolling(20).max().iloc[-1])
    ll = float(df["low"].rolling(20).min().iloc[-1])
    structure = "range"
    if close > hh * 0.995:
        structure = "breakout_up"
    elif close < ll * 1.005:
        structure = "breakdown"
    elif close > vwap:
        structure = "above_vwap"
    elif close < vwap:
        structure = "below_vwap"
    base["vwap20"] = vwap
    base["market_structure"] = structure
    base["regime"] = "trend_up" if base.get("score", 0) >= 3 else "trend_down" if base.get("score", 0) <= -3 else "range"
    base["volume"] = volume
    return base


# Add the advertised 2d macro context and use the richer analysis for bot requests.
if "2d" not in engine.TIMEFRAMES:
    engine.TIMEFRAMES = {
        "5m": engine.TIMEFRAMES["5m"],
        "10m": engine.TIMEFRAMES["10m"],
        "15m": engine.TIMEFRAMES["15m"],
        "30m": engine.TIMEFRAMES["30m"],
        "1h": engine.TIMEFRAMES["1h"],
        "4h": engine.TIMEFRAMES["4h"],
        "1d": engine.TIMEFRAMES["1d"],
        "2d": {"resolution": "2D", "minutes": 2880, "weight": 7, "role": "macro"},
    }
    engine.WEIGHTS = {k: v["weight"] for k, v in engine.TIMEFRAMES.items()}

engine.get_candles = get_candles
engine.timeframe_analysis = timeframe_analysis
