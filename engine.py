import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

DATA = Path("data")
DATA.mkdir(exist_ok=True)
JOURNAL = DATA / "journal.jsonl"
BASE_URL = "https://api.wallex.ir"
DEFAULT_SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
TIMEFRAMES = {"5m": "5", "15m": "15", "1h": "60", "4h": "240"}


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def save_event(event, payload):
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now_utc(), "event": event, "payload": payload}, ensure_ascii=False) + "\n")


def safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        value = float(value)
        return value if np.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def api_get(path, params=None, timeout=15):
    r = requests.get(
        BASE_URL + path,
        params=params or {},
        timeout=timeout,
        headers={"User-Agent": "TradingGuardian/1.2", "Accept": "application/json"},
    )
    r.raise_for_status()
    return r.json()


def wallex_snapshot(symbol=DEFAULT_SYMBOL):
    try:
        data = api_get("/v1/markets")
        item = data.get("result", {}).get("symbols", {}).get(symbol)
        if not item:
            return {"symbol": symbol, "error": f"Market {symbol} was not found on Wallex"}
        stats = item.get("stats", {})
        bid = safe_float(stats.get("bidPrice"))
        ask = safe_float(stats.get("askPrice"))
        last = safe_float(stats.get("lastPrice")) or ((bid + ask) / 2 if bid and ask else 0)
        return {
            "symbol": symbol, "bid": bid, "ask": ask, "last": last,
            "volume24h": safe_float(stats.get("24h_volume")),
            "quoteVolume24h": safe_float(stats.get("24h_quoteVolume")),
            "change24h": safe_float(stats.get("24h_ch")),
            "change7d": safe_float(stats.get("7d_ch")),
            "high24h": safe_float(stats.get("24h_highPrice")),
            "low24h": safe_float(stats.get("24h_lowPrice")),
        }
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc)}


def wallex_depth(symbol=DEFAULT_SYMBOL):
    try:
        result = api_get("/v1/depth", {"symbol": symbol}).get("result", {})
        bids, asks = result.get("bid", []), result.get("ask", [])
        bid_notional = sum(safe_float(x.get("sum")) for x in bids[:20])
        ask_notional = sum(safe_float(x.get("sum")) for x in asks[:20])
        total = bid_notional + ask_notional
        best_bid = safe_float(bids[0].get("price")) if bids else 0
        best_ask = safe_float(asks[0].get("price")) if asks else 0
        spread = best_ask - best_bid if best_bid and best_ask else 0
        mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
        return {
            "bid_notional_top20": bid_notional,
            "ask_notional_top20": ask_notional,
            "imbalance": (bid_notional - ask_notional) / total if total else 0,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "spread_pct": spread / mid * 100 if mid else 0,
        }
    except Exception as exc:
        return {"error": str(exc)}


def wallex_trades(symbol=DEFAULT_SYMBOL):
    try:
        trades = api_get("/v1/trades", {"symbol": symbol}).get("result", {}).get("latestTrades", [])
        buy = sum(safe_float(t.get("quantity")) for t in trades if t.get("isBuyOrder"))
        sell = sum(safe_float(t.get("quantity")) for t in trades if not t.get("isBuyOrder"))
        total = buy + sell
        return {"trade_count": len(trades), "buy_volume": buy, "sell_volume": sell, "buy_ratio": buy / total if total else 0.5}
    except Exception as exc:
        return {"error": str(exc), "buy_ratio": 0.5}


def wallex_candles(symbol=DEFAULT_SYMBOL, resolution="15", limit=300):
    end = int(time.time())
    start = end - int(resolution) * 60 * limit
    data = api_get("/v1/udf/history", {"symbol": symbol, "resolution": resolution, "from": start, "to": end})
    if data.get("s") != "ok":
        raise RuntimeError(str(data))
    keys = ["t", "o", "h", "l", "c", "v"]
    n = min(len(data.get(k, [])) for k in keys)
    if n < 220:
        raise RuntimeError("Not enough candles for EMA200")
    df = pd.DataFrame({"timestamp": data["t"][:n], "open": data["o"][:n], "high": data["h"][:n], "low": data["l"][:n], "close": data["c"][:n], "volume": data["v"][:n]})
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna().reset_index(drop=True)


def ema(s, period):
    return s.ewm(span=period, adjust=False).mean()


def rsi(s, period=14):
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df, period=14):
    prev = df.close.shift(1)
    tr = pd.concat([(df.high - df.low), (df.high - prev).abs(), (df.low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def indicators(df):
    out = df.copy()
    out["ema20"] = ema(out.close, 20)
    out["ema50"] = ema(out.close, 50)
    out["ema200"] = ema(out.close, 200)
    out["rsi"] = rsi(out.close)
    fast, slow = ema(out.close, 12), ema(out.close, 26)
    out["macd"] = fast - slow
    out["signal"] = ema(out.macd, 9)
    out["hist"] = out.macd - out.signal
    out["atr"] = atr(out)
    out["vma"] = out.volume.rolling(20).mean()
    out["vr"] = out.volume / out.vma.replace(0, np.nan)
    return out


def timeframe_score(df):
    x = indicators(df).iloc[-1]
    score, reasons = 0, []
    if x.close > x.ema20 > x.ema50 > x.ema200:
        score += 3; reasons.append("روند صعودی")
    elif x.close < x.ema20 < x.ema50 < x.ema200:
        score -= 3; reasons.append("روند نزولی")
    if x.rsi > 55:
        score += 1; reasons.append("RSI مثبت")
    elif x.rsi < 45:
        score -= 1; reasons.append("RSI منفی")
    if x.hist > 0:
        score += 1; reasons.append("MACD مثبت")
    elif x.hist < 0:
        score -= 1; reasons.append("MACD منفی")
    if safe_float(x.vr) > 1.2:
        score += 1 if score > 0 else -1
        reasons.append("حجم بالاتر از میانگین")
    return {"score": int(score), "price": float(x.close), "rsi": round(float(x.rsi), 2), "atr": float(x.atr), "ema20": float(x.ema20), "ema50": float(x.ema50), "ema200": float(x.ema200), "macd": float(x.macd), "hist": float(x.hist), "volume_ratio": round(safe_float(x.vr, 1), 2), "reasons": reasons}


def build_signal(symbol, market, depth, trades, analyses):
    weights = {"5m": 1, "15m": 2, "1h": 3, "4h": 4}
    valid = {tf: a for tf, a in analyses.items() if isinstance(a, dict) and "error" not in a and safe_float(a.get("atr")) > 0}
    missing = sorted(set(TIMEFRAMES) - set(valid))
    price = safe_float(market.get("last"))
    if not price:
        return {"symbol": symbol, "price": 0, "decision": "NO TRADE", "confidence": 0, "entry": None, "stop": None, "tp1": None, "tp2": None, "score": 0, "reason": market.get("error", "قیمت دریافت نشد"), "invalidation": "—"}
    if len(valid) < 3:
        return {"symbol": symbol, "price": price, "decision": "NO TRADE", "confidence": 0, "entry": None, "stop": None, "tp1": None, "tp2": None, "score": 0, "reason": "داده کافی نیست؛ تایم‌فریم ناقص: " + ", ".join(missing), "invalidation": "—", "timeframes": analyses}

    total = sum(a.get("score", 0) * weights.get(tf, 1) for tf, a in valid.items())
    imbalance = safe_float(depth.get("imbalance"))
    buy_ratio = safe_float(trades.get("buy_ratio"), 0.5)
    total += 1 if imbalance > 0.15 else -1 if imbalance < -0.15 else 0
    total += 1 if buy_ratio > 0.58 else -1 if buy_ratio < 0.42 else 0

    spread_pct = safe_float(depth.get("spread_pct"))
    max_spread = safe_float(os.getenv("MAX_SPREAD_PCT"), 0.5)
    if spread_pct > max_spread:
        return {"symbol": symbol, "price": price, "decision": "NO TRADE", "confidence": 0, "entry": None, "stop": None, "tp1": None, "tp2": None, "score": total, "reason": f"اسپرد زیاد است ({spread_pct:.3f}%)", "invalidation": "—", "timeframes": analyses}

    decision = "LONG" if total >= 6 else "SHORT" if total <= -6 else "NO TRADE"
    # Maximum theoretical score is 62: four timeframes x 6 points x their weights (1+2+3+4), plus 2 market microstructure points.
    max_score = sum(6 * weight for weight in weights.values()) + 2
    confidence = min(99, int(abs(total) / max_score * 100))
    atr_value = safe_float(valid.get("15m", next(iter(valid.values()))).get("atr")) or price * 0.005
    entry = stop = tp1 = tp2 = None
    if decision == "LONG":
        entry = price
        stop = entry - 1.5 * atr_value
        risk = entry - stop
        tp1 = entry + 1.5 * risk
        tp2 = entry + 2.5 * risk
    elif decision == "SHORT":
        entry = price
        stop = entry + 1.5 * atr_value
        risk = stop - entry
        tp1 = entry - 1.5 * risk
        tp2 = entry - 2.5 * risk

    reasons = [r for a in valid.values() for r in a.get("reasons", [])]
    rr1 = 1.5 if decision != "NO TRADE" else None
    rr2 = 2.5 if decision != "NO TRADE" else None
    return {"symbol": symbol, "decision": decision, "confidence": confidence, "entry": round(entry, 4) if entry else None, "stop": round(stop, 4) if stop else None, "tp1": round(tp1, 4) if tp1 else None, "tp2": round(tp2, 4) if tp2 else None, "score": total, "price": price, "risk_reward_tp1": rr1, "risk_reward_tp2": rr2, "reason": "؛ ".join(reasons[:10]) or "شرایط کافی نیست", "invalidation": "عبور از SL" if decision != "NO TRADE" else "—", "market": market, "orderbook": depth, "recent_trades": trades, "timeframes": analyses, "generated_at": now_utc()}


def get_signal_snapshot(symbol=DEFAULT_SYMBOL):
    try:
        market = wallex_snapshot(symbol)
        if market.get("error"):
            return {"symbol": symbol, "price": 0, "decision": "NO TRADE", "confidence": 0, "entry": None, "stop": None, "tp1": None, "tp2": None, "reason": market["error"], "invalidation": "—"}
        depth, trades = wallex_depth(symbol), wallex_trades(symbol)
        analyses = {}
        for tf, resolution in TIMEFRAMES.items():
            try:
                analyses[tf] = timeframe_score(wallex_candles(symbol, resolution, 300))
            except Exception as exc:
                analyses[tf] = {"error": str(exc), "score": 0, "reasons": []}
        result = build_signal(symbol, market, depth, trades, analyses)
        save_event("signal_generated", result)
        return result
    except Exception as exc:
        result = {"symbol": symbol, "price": 0, "decision": "NO TRADE", "confidence": 0, "entry": None, "stop": None, "tp1": None, "tp2": None, "reason": f"خطای موتور: {exc}", "invalidation": "—"}
        save_event("engine_error", result)
        return result


def paper_result(signal, high, low):
    """Evaluate a completed candle/range against a generated signal without placing orders."""
    if signal.get("decision") == "LONG":
        if safe_float(low) <= safe_float(signal.get("stop")):
            return "STOP"
        if safe_float(high) >= safe_float(signal.get("tp2")):
            return "TP2"
        if safe_float(high) >= safe_float(signal.get("tp1")):
            return "TP1"
    elif signal.get("decision") == "SHORT":
        if safe_float(high) >= safe_float(signal.get("stop")):
            return "STOP"
        if safe_float(low) <= safe_float(signal.get("tp2")):
            return "TP2"
        if safe_float(low) <= safe_float(signal.get("tp1")):
            return "TP1"
    return "OPEN"


def paper_stats():
    if not JOURNAL.exists():
        return {"closed": 0, "wins": 0, "stops": 0, "win_rate": 0.0}
    closed = wins = stops = 0
    with JOURNAL.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                item = json.loads(line)
                result = item.get("payload", {}).get("result") if item.get("event") == "paper_result" else None
                if result in {"TP1", "TP2", "STOP"}:
                    closed += 1
                    wins += result in {"TP1", "TP2"}
                    stops += result == "STOP"
            except (json.JSONDecodeError, TypeError):
                continue
    return {"closed": closed, "wins": wins, "stops": stops, "win_rate": round(wins / closed * 100, 2) if closed else 0.0}


def review_with_ai(client, snapshot):
    prompt = f"""گزارش Trading Guardian:\n{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n\nداده‌های روند، EMA، RSI، MACD، ATR، حجم و Order Book را بررسی کن. اعتبار LONG/SHORT یا دلیل NO TRADE را ارزیابی و ریسک‌ها و تناقض‌ها را بگو. هیچ سود تضمینی یا قطعیتی اعلام نکن. هیچ معامله واقعی انجام نده. پاسخ فارسی و ساختاریافته باشد."""
    response = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5.6"), tools=[{"type": "web_search"}], input=prompt)
    return response.output_text
