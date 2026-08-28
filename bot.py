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
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ALLOWED_USERS = {x.strip() for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()}
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


def authorized(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True
    user = update.effective_user
    return bool(user and str(user.id) in ALLOWED_USERS)


def keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Signal", callback_data="signal")],
        [InlineKeyboardButton("🤖 AI Review", callback_data="review")],
    ])


def format_signal(s):
    decision = s.get("decision", "NO TRADE")
    labels = {"LONG": "🟢 LONG", "SHORT": "🔴 SHORT", "NO TRADE": "⚪ NO TRADE"}
    lines = [
        f"📊 Trading Guardian — {s.get('symbol', '-')}",
        f"وضعیت: {labels.get(decision, decision)}",
        f"قیمت: {s.get('price', '-')}",
        f"امتیاز: {s.get('score', '-')}",
        f"اعتماد محاسباتی: {s.get('confidence', 0)}%",
    ]
    if decision != "NO TRADE":
        lines += [
            f"ورود: {s.get('entry')}",
            f"🛑 حد ضرر: {s.get('stop')}",
            f"🎯 تارگت ۱: {s.get('tp1')}",
            f"🎯 تارگت ۲: {s.get('tp2')}",
        ]
    lines += [f"دلیل: {s.get('reason', '—')}", f"ابطال: {s.get('invalidation', '—')}"]
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await update.message.reply_text("Unauthorized")
    await update.message.reply_text(
        "Trading Guardian — PAPER TRADING ONLY.\nسیگنال، حد ضرر و تارگت‌ها از داده بازار محاسبه می‌شوند.",
        reply_markup=keyboard(),
    )


async def signal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    try:
        snapshot = await asyncio.to_thread(get_signal_snapshot)
        save_event("telegram_signal", snapshot)
        text = format_signal(snapshot)
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=keyboard())
        else:
            await update.message.reply_text(text, reply_markup=keyboard())
    except Exception as exc:
        await (update.callback_query.message if update.callback_query else update.message).reply_text(
            f"⚠️ خطا در دریافت سیگنال: {exc}"
        )


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
        await target.chat.send_action(ChatAction.TYPING)
    if client is None:
        return await target.reply_text("OPENAI_API_KEY تنظیم نشده است.")
    try:
        snapshot = await asyncio.to_thread(get_signal_snapshot)
        result = await asyncio.to_thread(review_with_ai, client, snapshot)
        save_event("review", {"snapshot": snapshot, "result": result})
        await target.reply_text(result[:4000], reply_markup=keyboard())
    except Exception as exc:
        await target.reply_text(f"⚠️ خطا در بررسی AI: {exc}", reply_markup=keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    await update.message.reply_text(
        "/start — منوی اصلی\n/signal — دریافت سیگنال و تارگت‌ها\n/help — راهنما\n\nحالت پروژه: Paper Trading؛ اجرای معامله واقعی فعال نیست."
    )


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signal", signal))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(signal, pattern="^signal$"))
    app.add_handler(CallbackQueryHandler(review, pattern="^review$"))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
