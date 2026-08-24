import os, json
from datetime import datetime, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from openai import OpenAI
from engine import get_signal_snapshot, review_with_ai, save_event

load_dotenv()
TOKEN=os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
client=OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 تحلیل BTC", callback_data="signal")],
        [InlineKeyboardButton("🧠 اتصال به ChatGPT — بررسی و ارتقا", callback_data="review")],
        [InlineKeyboardButton("📒 گزارش عملکرد", callback_data="report")],
        [InlineKeyboardButton("🛡️ وضعیت ایمنی", callback_data="safety")],
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ ChatGPT Trading Guardian\\n\\nنسخه فعلی: PAPER TRADING\\n"
        "هیچ سفارش واقعی ارسال نمی‌شود.\\n\\nیک گزینه را انتخاب کن:",
        reply_markup=keyboard())

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    await q.answer()
    if q.data=="signal":
        snap=get_signal_snapshot()
        save_event("signal_snapshot", snap)
        await q.message.reply_text(format_signal(snap), reply_markup=keyboard())
    elif q.data=="review":
        snap=get_signal_snapshot()
        text=review_with_ai(client, snap)
        save_event("ai_review", {"snapshot":snap,"review":text})
        await q.message.reply_text("🧠 بررسی ChatGPT:\\n\\n"+text, reply_markup=keyboard())
    elif q.data=="report":
        await q.message.reply_text("📒 نسخه اولیه: ژورنال در data/journal.jsonl ثبت می‌شود.", reply_markup=keyboard())
    elif q.data=="safety":
        await q.message.reply_text(
            "🛡️ PAPER MODE فعال است.\\n"
            "برداشت وجه: متصل نیست.\\n"
            "معامله واقعی: غیرفعال.\\n"
            "تغییرات خودکار کد: غیرفعال؛ فقط پیشنهاد + تست.", reply_markup=keyboard())

def format_signal(s):
    return (
        f"📊 {s['symbol']}\\n"
        f"تصمیم: {s['decision']}\\n"
        f"قیمت مرجع: {s['price']:.2f}\\n"
        f"Entry: {s.get('entry','—')}\\n"
        f"SL: {s.get('stop','—')}\\n"
        f"TP1: {s.get('tp1','—')}\\n"
        f"TP2: {s.get('tp2','—')}\\n"
        f"Confidence: {s['confidence']}/100\\n\\n"
        f"دلایل: {s['reason']}\\n"
        f"ابطال: {s['invalidation']}"
    )

def main():
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling()

if __name__=="__main__":
    main()
