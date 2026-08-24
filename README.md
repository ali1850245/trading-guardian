# ChatGPT Trading Guardian v0.1

Telegram-first crypto analysis bot. PAPER TRADING ONLY.

Features:
- Telegram commands/buttons
- Independent signal engine (placeholder; must be backtested before live use)
- OpenAI "Review & Upgrade" button
- Web-search-enabled AI review through the OpenAI Responses API
- Signal journal and basic risk rules
- Wallex market-data adapter scaffold
- No withdrawal permission and no live-order execution in this version

## Setup
1. Create a Telegram bot with BotFather and copy its token.
2. Create an OpenAI API key.
3. Copy `.env.example` to `.env` and fill the keys.
4. `pip install -r requirements.txt`
5. `python bot.py`

The bot defaults to PAPER mode. Do not add exchange withdrawal permissions.
