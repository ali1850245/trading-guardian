# Trading Guardian v3 completion checklist

## Completed in the repository

- [x] Telegram dashboard and inline navigation
- [x] BTCUSDT / ETHUSDT / SOLUSDT selection
- [x] 5m / 10m / 15m / 30m / 1h / 4h / 1d multi-timeframe analysis
- [x] Hierarchy: macro -> structure -> setup -> trigger
- [x] Higher-timeframe context informs lower-timeframe timing without blindly forcing direction
- [x] Closed-candle analysis to reduce intrabar churn
- [x] EMA20 / EMA50 / EMA200
- [x] RSI / MACD / ATR / volume / momentum
- [x] Order Book imbalance and spread guard
- [x] Recent trade-flow context
- [x] Wallex primary data with Binance public fallback
- [x] Funding rate / Open Interest context when available
- [x] LONG / SHORT / NO TRADE gate with minimum data, timeframe alignment and macro/structure conflict blocking
- [x] Entry / SL / TP1 / TP2 / TP3 and R:R for Paper simulation
- [x] Scenario invalidation and per-symbol monitoring notifications
- [x] Paper journal, Win Rate, Profit Factor and PnL
- [x] Daily loss Kill Switch
- [x] OpenAI independent review
- [x] Explicit execution boundary (`execution.py`)
- [x] Exchange-neutral `OrderIntent` validation
- [x] Paper execution adapter with duplicate-intent protection
- [x] Explicit disabled live boundary that cannot place orders
- [x] CI compile/import/unit-test coverage for the execution boundary
- [x] No live order placement
- [x] No withdrawal functionality

## Important validation still required

These are validation tasks, not missing bot features:

1. Historical backtest on representative BTC/ETH/SOL datasets.
2. Walk-forward and out-of-sample validation.
3. Realistic fee and slippage assumptions.
4. Stress tests for missing data, API outages and extreme spreads.
5. A meaningful Paper Trading sample and drawdown review.
6. Independent code review before any live-capable experiment.

AI review remains advisory and must not silently modify or deploy the active strategy. Any future automated code change should be a reviewable patch and pass CI before merge.

## Safety boundary

Keep `MODE=paper`. Keep exchange credentials read-only or empty during evaluation. Never place secrets in GitHub files. This project does not guarantee signal accuracy, profit or a low error rate; the hierarchy is designed to reduce contradictory signals and avoid weak entries, not to eliminate market uncertainty.
