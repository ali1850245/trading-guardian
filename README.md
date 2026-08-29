# Trading Guardian v3

Telegram-first **paper-trading and market-analysis** bot. Live orders and withdrawals are disabled.

## Included

- BTCUSDT, ETHUSDT and SOLUSDT market selection
- Wallex primary market adapter with Binance public-data fallback
- Multi-timeframe analysis: 5m / 15m / 1h / 4h
- EMA20 / EMA50 / EMA200, RSI, MACD, ATR, volume and momentum
- Order Book imbalance, spread and recent trade flow
- Futures context: funding rate, open interest and recent liquidation data when public endpoints are available
- LONG / SHORT / NO TRADE decision gate with higher-timeframe agreement
- Entry, SL, TP1, TP2, TP3 and R:R calculations for simulation only
- Scenario invalidation text and signal-change monitoring
- Paper Trading journal, Win Rate, Profit Factor and PnL
- Configurable daily paper-loss Kill Switch
- OpenAI independent review through the Responses API
- Telegram inline menu for Dashboard, Market, Signal, AI Review, Paper, Performance, Safety, Settings and Help
- JSONL audit journal for generated signals and system events
- CI compilation/import/unit-test pipeline

## Safety boundary

This repository is intentionally **paper-only**. It does not contain live order placement or withdrawal code. Exchange API keys must never have withdrawal permission. Do not put real secrets in GitHub; use Raven Host Environment variables.

## Setup on Raven Host

1. Copy `.env.example` values into Raven Host Environment variables.
2. Set `TELEGRAM_BOT_TOKEN`.
3. Set `OPENAI_API_KEY` only if the AI Review button is wanted.
4. Keep `MODE=paper`.
5. Keep `WALLEX_API_KEY` empty unless a future read-only integration specifically requires it.
6. Start the server with `python bot.py`.

The default OpenAI model is `gpt-5.6`, which is supported by the Responses API. citeturn1search0

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

## Notes

The engine can fall back between public market-data sources. A missing derivatives endpoint never turns into invented data; the field stays unavailable. A weak or conflicting setup becomes `NO TRADE` rather than being forced into a direction.

Before relying on any strategy for real-world decisions, it should be independently tested on historical and out-of-sample data. This project is a software/paper-trading experiment, not a guarantee of market outcomes.
