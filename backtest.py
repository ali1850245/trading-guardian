"""Offline historical backtest helpers for Trading Guardian.

This module is intentionally paper-only: it never places exchange orders.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable

import pandas as pd


@dataclass
class BacktestResult:
    symbol: str
    candles: int
    trades: int
    wins: int
    losses: int
    win_rate: float
    pnl: float
    max_drawdown: float
    profit_factor: float
    tp1_hits: int = 0
    sl_hits: int = 0
    end_exits: int = 0

    def to_dict(self):
        return asdict(self)


def _signal_side(signal: dict) -> str:
    side = str(signal.get("decision", "NO TRADE")).upper()
    return side if side in {"LONG", "SHORT"} else "NO TRADE"


def run_backtest(
    frame: pd.DataFrame,
    symbol: str = "TEST",
    signal_fn: Callable | None = None,
    starting_balance: float = 10_000.0,
    fee_rate: float = 0.0,
    slippage_rate: float = 0.0,
) -> dict:
    """Run a conservative candle-by-candle paper backtest.

    ``signal_fn`` receives candles available up to the current candle and
    should return a Trading Guardian signal dictionary. A trade exits at the
    first subsequent candle touching SL or TP1. If neither is touched before
    the dataset ends, it is closed at the final close.

    ``fee_rate`` and ``slippage_rate`` are decimal fractions applied to both
    entry and exit notional, allowing more realistic paper evaluation without
    ever placing an exchange order.
    """
    required = {"open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if len(frame) < 3:
        return BacktestResult(symbol, len(frame), 0, 0, 0, 0.0, 0.0, 0.0, 0.0).to_dict()
    if signal_fn is None:
        raise ValueError("signal_fn is required for a strategy backtest")
    if starting_balance <= 0:
        raise ValueError("starting_balance must be positive")
    if fee_rate < 0 or slippage_rate < 0:
        raise ValueError("fee_rate and slippage_rate must be non-negative")

    df = frame.reset_index(drop=True).copy()
    equity = float(starting_balance)
    peak = equity
    max_dd = 0.0
    pnls = []
    tp1_hits = sl_hits = end_exits = 0
    i = 1
    while i < len(df) - 1:
        signal = signal_fn(df.iloc[:i].copy()) or {}
        side = _signal_side(signal)
        if side == "NO TRADE":
            i += 1
            continue
        entry = float(signal.get("entry") or df.iloc[i]["close"])
        stop = signal.get("stop")
        target = signal.get("tp1")
        if stop is None or target is None:
            i += 1
            continue
        stop, target = float(stop), float(target)
        exit_price = None
        reason = "end"
        j = i + 1
        while j < len(df):
            candle = df.iloc[j]
            if side == "LONG":
                # Conservative: when both levels occur in one candle, assume SL first.
                if float(candle.low) <= stop:
                    exit_price, reason = stop, "SL"
                    break
                if float(candle.high) >= target:
                    exit_price, reason = target, "TP1"
                    break
            else:
                if float(candle.high) >= stop:
                    exit_price, reason = stop, "SL"
                    break
                if float(candle.low) <= target:
                    exit_price, reason = target, "TP1"
                    break
            j += 1
        if exit_price is None:
            exit_price = float(df.iloc[-1]["close"])
            j = len(df) - 1

        # Model adverse slippage on both sides of the round trip.
        if side == "LONG":
            effective_entry = entry * (1 + slippage_rate)
            effective_exit = exit_price * (1 - slippage_rate)
            gross_pnl = effective_exit - effective_entry
        else:
            effective_entry = entry * (1 - slippage_rate)
            effective_exit = exit_price * (1 + slippage_rate)
            gross_pnl = effective_entry - effective_exit
        fees = (abs(effective_entry) + abs(effective_exit)) * fee_rate
        pnl = gross_pnl - fees

        if reason == "TP1":
            tp1_hits += 1
        elif reason == "SL":
            sl_hits += 1
        else:
            end_exits += 1
        pnls.append(float(pnl))
        equity += float(pnl)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        i = max(i + 1, j + 1)

    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    pf = gross_win / gross_loss if gross_loss else (999.0 if gross_win else 0.0)
    result = BacktestResult(
        symbol,
        len(df),
        len(pnls),
        wins,
        losses,
        round(wins / len(pnls) * 100, 2) if pnls else 0.0,
        round(sum(pnls), 8),
        round(max_dd, 8),
        round(pf, 3),
        tp1_hits,
        sl_hits,
        end_exits,
    )
    return result.to_dict()


def csv_loader(path: str) -> pd.DataFrame:
    """Load OHLCV CSV exported from an exchange or charting platform."""
    df = pd.read_csv(path)
    lower = {c.lower(): c for c in df.columns}
    rename = {}
    for wanted in ("timestamp", "open", "high", "low", "close", "volume"):
        if wanted in lower:
            rename[lower[wanted]] = wanted
    df = df.rename(columns=rename)
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"CSV needs {col} column")
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
