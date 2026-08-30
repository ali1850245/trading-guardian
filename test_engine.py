import math

from engine import build_signal, safe_float


def test_safe_float_handles_invalid_values():
    assert safe_float("12.5") == 12.5
    assert safe_float("") == 0.0
    assert safe_float("not-a-number", 7.0) == 7.0
    assert safe_float(float("nan"), 3.0) == 3.0


def test_build_signal_returns_no_trade_without_price():
    result = build_signal(
        "BTCUSDT",
        {"last": 0, "error": "price unavailable"},
        {},
        {},
        {},
    )
    assert result["decision"] == "NO TRADE"
    assert result["confidence"] == 0
    assert result["entry"] is None


def test_build_signal_long_has_protective_levels():
    analyses = {
        "5m": {"score": 2, "atr": 10, "reasons": []},
        "15m": {"score": 2, "atr": 10, "reasons": []},
        "1h": {"score": 2, "atr": 10, "reasons": []},
        "4h": {"score": 2, "atr": 10, "reasons": []},
    }
    result = build_signal(
        "BTCUSDT",
        {"last": 1000},
        {"imbalance": 0.2},
        {"buy_ratio": 0.6},
        analyses,
    )
    assert result["decision"] == "LONG"
    assert result["stop"] < result["entry"] < result["tp1"] < result["tp2"]
    assert math.isfinite(result["confidence"])
