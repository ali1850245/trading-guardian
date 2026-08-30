import asyncio
import os

from dotenv import load_dotenv
from openai import OpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

import runtime_extensions  # patches the core engine with 2d aggregation and richer context
from engine import (SYMBOLS, daily_risk_halted, get_signal_snapshot, paper_close,
                    paper_open, paper_records, paper_stats, paper_status, save_event)
from review import review_with_ai

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ALLOWED = {x.strip() for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip()}
MONITOR_CHAT_ID = os.getenv("TELEGRAM_MONITOR_CHAT_ID", "").strip()
MONITOR_INTERVAL = max(30, int(os.getenv("MONITOR_INTERVAL_SECONDS", "60")))
PAPER_AUTO_EXIT = os.getenv("PAPER_AUTO_EXIT", "true").lower() in {"1", "true", "yes", "on"}
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

if not TOKEN or any(ord(c) < 32 or ord(c) > 126 or c.isspace() for c in TOKEN):
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing or invalid")

def authorized(update):
    if not ALLOWED: return True
    u = update.effective_user
    return bool(u and str(u.id) in ALLOWED)

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 داشبورد", callback_data="dashboard"), InlineKeyboardButton("📡 بازار", callback_data="markets")],
        [InlineKeyboardButton("🟢 سیگنال", callback_data="signal"), InlineKeyboardButton("🧠 بررسی AI", callback_data="review")],
        [InlineKeyboardButton("📒 Paper", callback_data="paper"), InlineKeyboardButton("📈 عملکرد", callback_data="stats")],
        [InlineKeyboardButton("🔄 بروزرسانی", callback_data="refresh"), InlineKeyboardButton("🛡️ ایمنی", callback_data="safety")],
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="settings"), InlineKeyboardButton("❓ راهنما", callback_data="help")],
    ])

def kb_symbols():
    return InlineKeyboardMarkup([[InlineKeyboardButton(s, callback_data=f"sig:{s}") for s in SYMBOLS[:3]], [InlineKeyboardButton("⬅️ منوی اصلی", callback_data="home")]])

def fmt(v, digits=4):
    if v is None: return "—"
    try: return f"{float(v):,.{digits}f}"
    except Exception: return str(v)

def active_paper_positions():
    latest = {}
    for row in paper_records():
        tid = row.get("id")
        if tid: latest[tid] = row
    return [x for x in latest.values() if x.get("status") == "OPEN"]

def paper_text():
    p = paper_status(); active = active_paper_positions()
    text = ("📒 Paper Trading\n\n" f"سرمایه شروع: {fmt(p['balance_start'], 2)}\n" f"PnL بسته‌شده: {fmt(p['pnl'], 2)}\n" f"بسته‌شده: {p['closed']} | Win Rate: {p['win_rate']}%\n" f"Profit Factor: {p['profit_factor']}\n" f"پوزیشن باز واقعی در دفتر: {len(active)}\n\n")
    if active:
        text += "پوزیشن‌های باز:\n" + "\n".join(f"• {x['id']} | {x['symbol']} {x['side']} | Entry {fmt(x['entry'])} | SL {fmt(x['stop'])} | TP1 {fmt(x['tp1'])}" for x in active[:10])
    else: text += "پوزیشن بازی ثبت نشده است."
    return text

def format_signal(s):
    d=s.get("decision","NO TRADE"); label={"LONG":"🟢 LONG","SHORT":"🔴 SHORT","NO TRADE":"🟡 NO TRADE"}.get(d,d)
    lines=[f"📊 Trading Guardian | {s.get('symbol','-')}",f"تصمیم: {label}",f"قیمت: {fmt(s.get('price'))}",f"امتیاز: {s.get('score','—')}",f"اطمینان محاسباتی: {s.get('confidence',0)}%"]
    if d!="NO TRADE": lines += [f"Entry: {fmt(s.get('entry'))}",f"🛑 SL: {fmt(s.get('stop'))}",f"🎯 TP1: {fmt(s.get('tp1'))} | R:R {s.get('risk_reward_tp1','—')}",f"🎯 TP2: {fmt(s.get('tp2'))} | R:R {s.get('risk_reward_tp2','—')}",f"🎯 TP3: {fmt(s.get('tp3'))} | R:R {s.get('risk_reward_tp3','—')}"]
    der=s.get("derivatives",{})
    lines += [f"Funding: {fmt(der.get('funding_rate'),6)} | OI: {fmt(der.get('open_interest'),2)}",f"دلیل: {s.get('reason','—')}",f"ابطال: {s.get('invalidation','—')}","⚠️ خروجی فقط Paper/تحلیلی است؛ سفارش واقعی فعال نیست."]
    return "\n".join(lines)

def dashboard_text():
    p=paper_status()
    return ("🛡️ Trading Guardian\n\nحالت: 📒 PAPER TRADING\n" f"سرمایه مجازی شروع: {fmt(p['balance_start'],2)}\nPnL ثبت‌شده: {fmt(p['pnl'],2)}\n" f"معاملات بسته: {p['closed']} | Win Rate: {p['win_rate']}%\n" f"Profit Factor: {p['profit_factor']}\nپوزیشن‌های باز: {len(active_paper_positions())}\n" f"Kill Switch روزانه: {'🔴 فعال' if p['kill_switch'] else '🟢 آماده'}\n\n" "سفارش واقعی و برداشت وجه در این نسخه فعال نیست.")

def stats_text():
    s=paper_stats(); return ("📈 عملکرد Paper\n\n" f"بسته‌شده: {s['closed']}\nبرد: {s['wins']}\nباخت: {s['losses']}\n" f"Win Rate: {s['win_rate']}%\nProfit Factor: {s['profit_factor']}\nPnL: {fmt(s['pnl'],2)}")

def markets_text(): return "📡 بازارهای فعال\n\n" + "\n".join(f"• {s}" for s in SYMBOLS) + "\n\nداده عمومی بازار از Wallex و Binance استفاده می‌شود."
def safety_text():
    p=paper_status(); return ("🛡️ وضعیت ایمنی\n\nحالت: PAPER ONLY\nسفارش واقعی: خاموش\nبرداشت: متصل نیست\n" f"Daily loss limit: {p['daily_loss_limit_pct']}%\nKill Switch: {'🔴 فعال' if p['kill_switch'] else '🟢 آماده'}\n" f"Auto Paper Exit: {'🟢 روشن' if PAPER_AUTO_EXIT else '⚪ خاموش'}\n" "اصلاح خودکار کد از داخل ربات: خاموش\nAI فقط برای بررسی و توضیح است.")
def help_text(): return ("❓ راهنما\n\n/start — منوی اصلی\n/signal — انتخاب نماد و تحلیل\n/stats — عملکرد Paper\n/paper — پوزیشن‌های Paper\n/health — سلامت سرویس\n/help — راهنما\n\n" "مانیتور بازار و خروج خودکار فقط در Paper انجام می‌شود؛ سفارش واقعی وجود ندارد.")

async def start(update, context):
    if authorized(update): await update.message.reply_text("🛡️ Trading Guardian آماده است.\nحالت فعلی: PAPER TRADING", reply_markup=kb_main())

async def send_signal(target, symbol):
    try:
        s=await asyncio.to_thread(get_signal_snapshot, symbol); save_event("telegram_signal",s); buttons=[]
        if s.get("decision") in {"LONG","SHORT"} and not daily_risk_halted(): buttons.append(InlineKeyboardButton("📒 ثبت در Paper",callback_data=f"paperopen:{symbol}"))
        buttons += [InlineKeyboardButton("🔄 دوباره",callback_data=f"sig:{symbol}"), InlineKeyboardButton("⬅️ بازار",callback_data="markets")]
        await target.reply_text(format_signal(s),reply_markup=InlineKeyboardMarkup([buttons,[InlineKeyboardButton("🏠 خانه",callback_data="home")]]))
    except Exception as e: await target.reply_text(f"⚠️ خطا: {e}",reply_markup=kb_main())

async def callback(update, context):
    q=update.callback_query
    if not authorized(update): return await q.answer()
    await q.answer(); data=q.data
    if data in {"home","dashboard"}: return await q.edit_message_text(dashboard_text(),reply_markup=kb_main())
    if data=="refresh":
        await q.edit_message_text("🔄 در حال دریافت داده تازه...",reply_markup=kb_main()); return await send_signal(q.message,os.getenv("SYMBOL",SYMBOLS[0]))
    if data=="markets": return await q.edit_message_text(markets_text(),reply_markup=kb_symbols())
    if data=="stats": return await q.edit_message_text(stats_text(),reply_markup=kb_main())
    if data=="paper": return await q.edit_message_text(paper_text(),reply_markup=kb_main())
    if data=="safety": return await q.edit_message_text(safety_text(),reply_markup=kb_main())
    if data=="help": return await q.edit_message_text(help_text(),reply_markup=kb_main())
    if data=="settings": return await q.edit_message_text("⚙️ تنظیمات\n\nنماد پیش‌فرض: "+os.getenv("SYMBOL","BTCUSDT")+"\nبازه مانیتور: "+str(MONITOR_INTERVAL)+" ثانیه\nAuto Paper Exit: "+str(PAPER_AUTO_EXIT)+"\n\nکلیدها فقط از Environment خوانده می‌شوند.",reply_markup=kb_main())
    if data=="signal": return await q.edit_message_text("🟢 نماد را انتخاب کن:",reply_markup=kb_symbols())
    if data=="review":
        if client is None: return await q.edit_message_text("⚠️ OPENAI_API_KEY تنظیم نشده است.",reply_markup=kb_main())
        await q.edit_message_text("🧠 در حال بررسی آخرین وضعیت...",reply_markup=kb_main()); await q.message.chat.send_action(ChatAction.TYPING)
        try:
            s=await asyncio.to_thread(get_signal_snapshot); result=await asyncio.to_thread(review_with_ai,client,s); save_event("review",{"snapshot":s,"result":result}); await q.message.reply_text(result[:4000],reply_markup=kb_main())
        except Exception as e: await q.message.reply_text(f"⚠️ خطای AI: {e}",reply_markup=kb_main())
        return
    if data.startswith("sig:"):
        await q.message.chat.send_action(ChatAction.TYPING); return await send_signal(q.message,data.split(":",1)[1])
    if data.startswith("paperopen:"):
        symbol=data.split(":",1)[1]; s=await asyncio.to_thread(get_signal_snapshot,symbol); result=await asyncio.to_thread(paper_open,s,1.0)
        return await q.message.reply_text(("✅ در Paper ثبت شد.\n" if result.get("ok") else "⚠️ ثبت نشد: ") + (str(result.get("trade")) if result.get("ok") else result.get("reason","—")),reply_markup=kb_main())

async def signal_cmd(update,context):
    if authorized(update): await update.message.reply_text("🟢 نماد را انتخاب کن:",reply_markup=kb_symbols())
async def stats_cmd(update,context):
    if authorized(update): await update.message.reply_text(stats_text(),reply_markup=kb_main())
async def paper_cmd(update,context):
    if authorized(update): await update.message.reply_text(paper_text(),reply_markup=kb_main())
async def health(update,context):
    if authorized(update): await update.message.reply_text("🟢 Bot process: OK\n🟢 Paper engine: available\n🟢 Live orders: DISABLED\n🟢 Withdrawals: DISABLED",reply_markup=kb_main())
async def help_cmd(update,context):
    if authorized(update): await update.message.reply_text(help_text(),reply_markup=kb_main())

async def monitor_loop(app):
    if not MONITOR_CHAT_ID: return
    last_by_symbol={}
    while True:
        try:
            for symbol in SYMBOLS:
                s=await asyncio.to_thread(get_signal_snapshot,symbol); sig=(symbol,s.get("decision"),s.get("entry"),s.get("stop"),s.get("tp1"),s.get("tp2"),s.get("tp3"))
                if s.get("decision")!="NO TRADE" and sig != last_by_symbol.get(symbol):
                    await app.bot.send_message(chat_id=MONITOR_CHAT_ID,text=format_signal(s),reply_markup=kb_main()); last_by_symbol[symbol]=sig
                if PAPER_AUTO_EXIT:
                    for trade in active_paper_positions():
                        if trade.get("symbol") != symbol: continue
                        price=s.get("price")
                        if price is None: continue
                        side=trade.get("side"); stop,tp1=float(trade.get("stop")),float(trade.get("tp1"))
                        hit=(side=="LONG" and (price<=stop or price>=tp1)) or (side=="SHORT" and (price>=stop or price<=tp1))
                        if hit:
                            reason="SL" if (side=="LONG" and price<=stop) or (side=="SHORT" and price>=stop) else "TP1"
                            closed=await asyncio.to_thread(paper_close,trade,float(price),reason)
                            await app.bot.send_message(chat_id=MONITOR_CHAT_ID,text=f"📒 Paper {reason}\n{trade['symbol']} {trade['side']}\nExit: {fmt(closed['exit'])}\nPnL: {fmt(closed['pnl'],4)}")
                save_event("monitor_tick",s)
        except Exception as e: save_event("monitor_error",{"error":str(e)})
        await asyncio.sleep(MONITOR_INTERVAL)

async def post_init(app): app.create_task(monitor_loop(app),name="market-monitor")
def main():
    app=Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("signal",signal_cmd)); app.add_handler(CommandHandler("stats",stats_cmd)); app.add_handler(CommandHandler("paper",paper_cmd)); app.add_handler(CommandHandler("health",health)); app.add_handler(CommandHandler("help",help_cmd)); app.add_handler(CallbackQueryHandler(callback)); app.run_polling(drop_pending_updates=True)
if __name__=="__main__": main()
