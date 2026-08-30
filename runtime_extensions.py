"""Runtime extensions kept separate from the core engine to make upgrades reviewable."""
from __future__ import annotations

import engine

_original_get_candles = engine.get_candles
_original_higher_context = engine.higher_timeframe_context


def get_candles(symbol=engine.DEFAULT_SYMBOL, resolution="15", limit=300):
    if str(resolution) != "2D":
        return _original_get_candles(symbol, resolution, limit)
    daily = _original_get_candles(symbol, "1D", max(limit * 2 + 4, engine.MIN_CANDLES))
    if len(daily) < 2:
        raise RuntimeError("Not enough daily candles for 2d aggregation")
    frame = daily.copy().reset_index(drop=True)
    frame["group"] = frame.index // 2
    return frame.groupby("group", sort=True).agg(
        timestamp=("timestamp", "first"), open=("open", "first"),
        high=("high", "max"), low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index(drop=True).tail(limit).reset_index(drop=True)


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
    if close >= hh:
        structure = "breakout_up"
    elif close <= ll:
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


def higher_timeframe_context(analyses):
    macro_names = ("2d", "1d")
    structure_names = ("1h", "4h")
    macro = [analyses.get(x, {}).get("score", 0) for x in macro_names if not analyses.get(x, {}).get("error")]
    structure = [analyses.get(x, {}).get("score", 0) for x in structure_names if not analyses.get(x, {}).get("error")]
    direction = engine._direction
    macro_dir = direction(sum(macro) / len(macro), 2) if macro else 0
    structure_dir = direction(sum(structure) / len(structure), 2) if structure else 0
    if macro_dir and structure_dir and macro_dir == structure_dir:
        bias = macro_dir
    elif macro_dir and not structure_dir:
        bias = macro_dir
    elif structure_dir and not macro_dir:
        bias = structure_dir
    else:
        bias = 0
    return {"macro_direction": macro_dir, "structure_direction": structure_dir, "bias": bias,
            "macro_score": round(sum(macro) / len(macro), 3) if macro else 0,
            "structure_score": round(sum(structure) / len(structure), 3) if structure else 0,
            "macro_timeframes": list(macro_names), "structure_timeframes": list(structure_names)}


if "2d" not in engine.TIMEFRAMES:
    engine.TIMEFRAMES = {
        "5m": engine.TIMEFRAMES["5m"], "10m": engine.TIMEFRAMES["10m"],
        "15m": engine.TIMEFRAMES["15m"], "30m": engine.TIMEFRAMES["30m"],
        "1h": engine.TIMEFRAMES["1h"], "4h": engine.TIMEFRAMES["4h"],
        "1d": engine.TIMEFRAMES["1d"],
        "2d": {"resolution": "2D", "minutes": 2880, "weight": 7, "role": "macro"},
    }
    engine.WEIGHTS = {k: v["weight"] for k, v in engine.TIMEFRAMES.items()}

engine.get_candles = get_candles
engine.timeframe_analysis = timeframe_analysis
engine.higher_timeframe_context = higher_timeframe_context
