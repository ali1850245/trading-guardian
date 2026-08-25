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

TOKEN = "".join(os.getenv("TELEGRAM_BOT_TOKEN", "").split())
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ALLOWED_USERS = {
    x.strip() for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()
}
JOURNAL = Path("data/journal.jsonl")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None


def authorized(update: Update) -> bool:
    if not ALLOWED_USERS:
        return True
    user = update.effective_user
    return bool(user and str(user.id) in ALLOWED_USERS)


def keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 تحلیل BTC", callback_data="signal")],
        [InlineKeyboardButton("🧠 بررسی با ChatGPT", callback_data="review")],
        [InlineKeyboardButton("📒 گزارش عملکرد", callback_data="report")],
        [InlineKeyboardButton("🛡️ وضعیت ایمنی", callback_data="safety")],
    ])


def format_signal(s):
    price = s.get("price", 0) or 0
    return (
        f"📊 {s.get('symbol', 'BTCUSDT')}\n"
        f"تصمیم: {s.get('decision', 'NO TRADE')}\n"
        f"قیمت مرجع: {price:.2f}\n"
        f"Entry: {s.get('entry', '—')}\n"
        f"SL: {s.get('stop', '—')}\n"
        f"TP1: {s.get('tp1', '—')}\n"
        f"TP2: {s.get('tp2', '—')}\n"
        f"Confidence: {s.get('confidence', 0)}/100\n\n"
        f"دلایل: {s.get('reason', '—')}\n"
        f"ابطال: {s.get('invalidation', '—')}"
    )


async def safe_reply(message, text, **kwargs):
    if len(text) <= 4000:
        await message.reply_text(text, **kwargs)
        return
    for i in range(0, len(text), 4000):
        await message.reply_text(text[i:i + 4000], **kwargs if i == 0 else {})


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        await update.message.reply_text("⛔ دسترسی مجاز نیست.")
        return
    await update.message.reply_text(
        "🛡️ ChatGPT Trading Guardian\n\n"
        "نسخه فعلی: PAPER TRADING\n"
        "هیچ سفارش واقعی ارسال نمی‌شود.\n\n"
        "یک گزینه را انتخاب کن:",
        reply_markup=keyboard(),
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not authorized(update):
        await q.answer("دسترسی مجاز نیست.", show_alert=True)
        return
    await q.answer()

    try:
        await q.message.chat.send_action(ChatAction.TYPING)
        if q.data == "signal":
            snap = await asyncio.to_thread(get_signal_snapshot)
            save_event("signal_snapshot", snap)
            await safe_reply(q.message, format_signal(snap), reply_markup=keyboard())

        elif q.data == "review":
            if not client:
                await safe_reply(q.message, "⚠️ OPENAI_API_KEY تنظیم نشده است.", reply_markup=keyboard())
                return
            snap = await asyncio.to_thread(get_signal_snapshot)
            text = await asyncio.to_thread(review_with_ai, client, snap)
            save_event("ai_review", {"snapshot": snap, "review": text})
            await safe_reply(q.message, "🧠 بررسی ChatGPT:\n\n" + text, reply_markup=keyboard())

        elif q.data == "report":
            if not JOURNAL.exists():
                text = "📒 هنوز گزارشی ثبت نشده است."
            else:
                lines = JOURNAL.read_text(encoding="utf-8").splitlines()
                text = f"📒 تعداد رویدادهای ثبت‌شده: {len(lines)}\n"
                text += "آخرین رویدادها:\n" + "\n".join(lines[-5:])
            await safe_reply(q.message, text, reply_markup=keyboard())

        elif q.data == "safety":
            await safe_reply(
                q.message,
                "🛡️ PAPER MODE فعال است.\n"
                "برداشت وجه: متصل نیست.\n"
                "معامله واقعی: غیرفعال.\n"
                "تغییر خودکار کد: غیرفعال.\n"
                "⚠️ این ربات ابزار تحلیل است و سیگنال آن تضمین سود نیست.",
                reply_markup=keyboard(),
            )
    except Exception as exc:
        save_event("bot_error", {"error": str(exc), "callback": q.data})
        await safe_reply(q.message, "⚠️ خطایی هنگام پردازش رخ داد. جزئیات در journal ثبت شد.", reply_markup=keyboard())


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    save_event("telegram_error", {"error": repr(error)})


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_error_handler(error_handler)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
