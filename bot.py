import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from engine import get_signal_snapshot, review_with_ai, save_event

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if TOKEN and any(ch.isspace() or ord(ch) < 32 or ord(ch) > 126 for ch in TOKEN):
    TOKEN = ""

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing. Configure it as a Codespaces environment variable or GitHub Actions secret.")

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ALLOWED_USERS = {x.strip() for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()}
JOURNAL = Path("data/journal.jsonl")

client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


def authorized(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True
    user = update.effective_user
    return bool(user and str(user.id) in ALLOWED_USERS)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await update.message.reply_text("Unauthorized")
    keyboard = [[InlineKeyboardButton("📊 Signal", callback_data="signal"), InlineKeyboardButton("🤖 Review & Upgrade", callback_data="review")]]
    await update.message.reply_text(
        "Trading Guardian — PAPER TRADING ONLY.\nChoose an action:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    snapshot = get_signal_snapshot()
    save_event("signal", snapshot)
    text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(f"Signal snapshot:\n```\n{text}\n```", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Signal snapshot:\n```\n{text}\n```", parse_mode="Markdown")


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.chat.send_action(ChatAction.TYPING)
        target = update.callback_query.message
    else:
        target = update.message
    if client is None:
        return await target.reply_text("OPENAI_API_KEY is missing.")
    result = review_with_ai(client, get_signal_snapshot())
    save_event("review", result)
    await target.reply_text(result[:4000])


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CallbackQueryHandler(signal, pattern="^signal$"))
    app.add_handler(CallbackQueryHandler(review, pattern="^review$"))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
