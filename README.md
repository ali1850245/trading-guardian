# Trading Guardian v3

Telegram-first **paper-trading and market-analysis** bot. Live orders and withdrawals are disabled.

## Included

- BTCUSDT, ETHUSDT and SOLUSDT market selection
- Wallex primary market adapter with Binance public-data fallback
- Multi-timeframe analysis: **5m / 10m / 15m / 30m / 1h / 4h / 1d / 2d**
- Hierarchical timeframe logic: 2d/1d macro context -> 4h/1h structure -> 30m/15m setup -> 10m/5m trigger
- Higher timeframes inform lower timeframes; they do not blindly force a direction
- Closed-candle analysis to reduce intrabar signal churn
- EMA20 / EMA50 / EMA200, RSI, MACD, ATR, volume and momentum
- Order Book imbalance, spread and recent trade flow
- Futures context: funding rate, open interest and recent liquidation data when public endpoints are available
- LONG / SHORT / NO TRADE decision gate with minimum data requirements, timeframe alignment and conflict blocking
- Entry, SL, TP1, TP2, TP3 and R:R calculations for simulation only
- Scenario invalidation text and change monitoring
- Paper Trading journal, Win Rate, Profit Factor and PnL
- Configurable daily paper-loss Kill Switch
- OpenAI independent review through the Responses API
- Telegram inline menu for Dashboard, Markets, Signal, AI Review, Paper Trading, Performance, Safety, Settings and Help
- JSONL audit journal for generated signals and system events
- CI compilation, import and unit-test pipeline

## Safety boundary

This repository is intentionally **paper-only**. It does not contain live order placement or withdrawal code. Exchange API keys must never have withdrawal permission. Do not put real secrets in GitHub; use Raven Host Environment variables.

## Setup on Raven Host

1. Copy `.env.example` values into Raven Host Environment variables.
2. Set `TELEGRAM_BOT_TOKEN`.
3. Set `OPENAI_API_KEY` only if the AI Review button is wanted.
4. Keep `MODE=paper`.
5. Keep `WALLEX_API_KEY` empty unless a future read-only integration specifically requires it.
6. Start the server with `python bot.py`.

The engine uses public market data and keeps AI review advisory. No model output is treated as a guaranteed probability or automatic trade instruction.

## Telegram menu

`/start` opens the main dashboard. The inline menu provides:

- 📊 Dashboard
- 📡 Markets
- 🟢 Signal
- 🧠 AI Review
- 📒 Paper Trading
- 📈 Performance
- 🛡️ Safety / Kill Switch
- ⚙️ Settings
- ❓ Help

## Timeframe hierarchy

The engine deliberately separates context from timing:

1. **2d + 1d:** macro direction and broad market bias.
2. **4h + 1h:** market structure and confirmation.
3. **30m + 15m:** setup quality.
4. **10m + 5m:** entry timing/trigger context.

If macro and structure directly conflict, the engine returns `NO TRADE`. If lower-timeframe conditions strongly contradict the higher-timeframe context, the setup is also rejected. This reduces contradictory signals rather than pretending that every timeframe must agree.

## Notes

The engine can fall back between public market-data sources. A missing derivatives endpoint never becomes invented data; the field stays unavailable. Weak, conflicting or insufficient setups become `NO TRADE` rather than being forced into a direction.

Two-day candles are constructed from daily public candles when a native 2d endpoint is not available. The engine uses closed candles for analysis where possible.

Before relying on any strategy for real-world decisions, it should be independently tested on historical and out-of-sample data. This project is a software/paper-trading experiment, not a guarantee of market outcomes.
