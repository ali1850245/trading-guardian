## Upgrade pipeline

The Review & Upgrade button is intentionally gated.

AI can:
- inspect recent signals and failures
- use web search for current technical information/news
- propose filters, features and parameter changes

AI cannot directly deploy code or enable live trading.

Safe pipeline:
1. AI review
2. Generate a patch in a separate branch
3. Unit tests
4. Historical backtest
5. Walk-forward / out-of-sample test
6. Paper trading
7. Compare against current version
8. Human approval
9. Deploy

Recommended later data:
- Wallex WebSocket order book/trades
- global spot/futures prices
- OI/funding/liquidations
- volatility and spreads
- news/events
