"""Execution boundary for Trading Guardian.

The repository remains paper-only.  This module makes the execution boundary
explicit so signal generation is separated from order execution without
containing live exchange-order placement code.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Mapping, Protocol
import time


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE_DISABLED = "live_disabled"


class ExecutionBlocked(RuntimeError):
    """Raised when an execution path is intentionally unavailable."""


@dataclass(frozen=True)
class OrderIntent:
    """Normalized order intent produced from a validated signal.

    This is deliberately exchange-neutral.  It does not contain credentials,
    signatures, or an exchange request implementation.
    """

    symbol: str
    side: str
    quantity: float
    entry: float
    stop: float
    tp1: float | None = None
    tp2: float | None = None
    tp3: float | None = None
    signal_id: str | None = None

    def validate(self) -> None:
        if self.side not in {"LONG", "SHORT"}:
            raise ValueError("side must be LONG or SHORT")
        if not self.symbol:
            raise ValueError("symbol is required")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.entry <= 0 or self.stop <= 0:
            raise ValueError("entry and stop must be positive")
        if self.side == "LONG" and self.stop >= self.entry:
            raise ValueError("LONG stop must be below entry")
        if self.side == "SHORT" and self.stop <= self.entry:
            raise ValueError("SHORT stop must be above entry")
        targets = [x for x in (self.tp1, self.tp2, self.tp3) if x is not None]
        if any(x <= 0 for x in targets):
            raise ValueError("targets must be positive")
        if self.side == "LONG" and any(x <= self.entry for x in targets):
            raise ValueError("LONG targets must be above entry")
        if self.side == "SHORT" and any(x >= self.entry for x in targets):
            raise ValueError("SHORT targets must be below entry")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionAdapter(Protocol):
    mode: ExecutionMode

    def submit(self, intent: OrderIntent) -> dict[str, Any]: ...


class PaperExecutionAdapter:
    """Deterministic paper adapter used by the project."""

    mode = ExecutionMode.PAPER

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def submit(self, intent: OrderIntent) -> dict[str, Any]:
        intent.validate()
        key = intent.signal_id or f"{intent.symbol}:{intent.side}:{intent.entry}:{intent.quantity}"
        if key in self._seen:
            return {"ok": False, "mode": self.mode.value, "reason": "duplicate paper intent", "idempotent": True}
        self._seen.add(key)
        return {
            "ok": True,
            "mode": self.mode.value,
            "status": "PAPER_OPEN",
            "order_id": f"paper-{int(time.time() * 1000)}",
            "intent": intent.to_dict(),
        }


class LiveExecutionAdapter:
    """Explicit disabled boundary; it intentionally cannot place live orders."""

    mode = ExecutionMode.LIVE_DISABLED

    def submit(self, intent: OrderIntent) -> dict[str, Any]:
        intent.validate()
        raise ExecutionBlocked(
            "Live order execution is disabled in Trading Guardian. "
            "Use PaperExecutionAdapter for testing."
        )


def intent_from_signal(signal: Mapping[str, Any], quantity: float) -> OrderIntent:
    """Convert a LONG/SHORT signal into a validated, exchange-neutral intent."""
    decision = str(signal.get("decision", "NO TRADE")).upper()
    if decision not in {"LONG", "SHORT"}:
        raise ValueError("signal is not executable: expected LONG or SHORT")
    intent = OrderIntent(
        symbol=str(signal.get("symbol", "")).upper(),
        side=decision,
        quantity=float(quantity),
        entry=float(signal["entry"]),
        stop=float(signal["stop"]),
        tp1=float(signal["tp1"]) if signal.get("tp1") is not None else None,
        tp2=float(signal["tp2"]) if signal.get("tp2") is not None else None,
        tp3=float(signal["tp3"]) if signal.get("tp3") is not None else None,
        signal_id=str(signal.get("signal_id")) if signal.get("signal_id") else None,
    )
    intent.validate()
    return intent
