# Trading Guardian v3 upgrade checklist

## Completed in the repository

- [x] Telegram dashboard and inline navigation
- [x] BTCUSDT / ETHUSDT / SOLUSDT selection
- [x] 5m / 15m / 1h / 4h multi-timeframe analysis
- [x] EMA20 / EMA50 / EMA200
- [x] RSI / MACD / ATR / volume / momentum
- [x] Order Book imbalance and spread guard
- [x] Recent trade-flow context
- [x] Wallex primary data with Binance public fallback
- [x] Funding rate / Open Interest / recent liquidation context when available
- [x] LONG / SHORT / NO TRADE gate with 1h + 4h agreement
- [x] Entry / SL / TP1 / TP2 / TP3 and R:R for Paper simulation
- [x] Scenario invalidation and monitoring notifications
- [x] Paper journal, Win Rate, Profit Factor and PnL
- [x] Daily loss Kill Switch
- [x] OpenAI independent review
- [x] CI compile/import/unit tests
- [x] No live order placement
- [x] No withdrawal functionality

## Required before any future live-capable branch

1. Historical backtest on a representative dataset.
2. Walk-forward and out-of-sample validation.
3. Slippage/fee assumptions and stress tests.
4. Minimum paper-trading sample and drawdown review.
5. Independent code review.
6. Explicit human approval and a separate branch.
7. Exchange credentials isolated from the paper bot.
8. Read-only credentials during evaluation.

AI review must remain advisory. It must not silently modify or deploy the active strategy. Any future automated code change should be generated as a reviewable patch and pass CI before merge.
