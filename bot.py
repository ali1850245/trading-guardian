import asyncio, os
from dotenv import load_dotenv
from openai import OpenAI
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from engine import SYMBOLS, TIMEFRAMES, daily_risk_halted, get_signal_snapshot, paper_close, paper_open, paper_records, paper_stats, paper_status, save_event
from review import review_with_ai

load_dotenv()
TOKEN=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
OPENAI_KEY=os.getenv("OPENAI_API_KEY","").strip()
DEFAULT_SYMBOL=os.getenv("SYMBOL", SYMBOLS[0] if SYMBOLS else "BTCUSDT")
MONITOR_CHAT_ID=os.getenv("TELEGRAM_MONITOR_CHAT_ID","").strip()
MONITOR_INTERVAL=max(30,int(os.getenv("MONITOR_INTERVAL_SECONDS","60")))
PAPER_AUTO_EXIT=os.getenv("PAPER_AUTO_EXIT","true").lower() in {"1","true","yes","on"}
OPENAI_MODEL=os.getenv("OPENAI_MODEL","gpt-5.6").strip() or "gpt-5.6"
client=OpenAI(api_key=OPENAI_KEY,timeout=20.0,max_retries=1) if OPENAI_KEY else None
if not TOKEN or any(ord(c)<32 or ord(c)>126 or c.isspace() for c in TOKEN): raise RuntimeError("TELEGRAM_BOT_TOKEN is missing or invalid")
ALLOWED={x.strip() for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS","").split(",") if x.strip()}
TIMEFRAME_KEYS=tuple(TIMEFRAMES.keys())
PAPER_LEVERAGES=(1,2,3,5,10)

def auth(update): return not ALLOWED or (update.effective_user and str(update.effective_user.id) in ALLOWED)
def fmt(v,d=4):
    if v is None:return "—"
    try:return f"{float(v):,.{d}f}"
    except:return str(v)
def active():
    latest={}
    for r in paper_records():
        if r.get("id"):latest[r["id"]]=r
    return [r for r in latest.values() if r.get("status")=="OPEN"]
def home_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 تحلیل جامع",callback_data="analysis"),InlineKeyboardButton("📡 بازار",callback_data="markets")],
        [InlineKeyboardButton("🎯 سیگنال + TP/SL",callback_data="signal"),InlineKeyboardButton("🧠 AI Review",callback_data="review")],
        [InlineKeyboardButton("📒 Paper Trading",callback_data="paper"),InlineKeyboardButton("📈 عملکرد",callback_data="stats")],
        [InlineKeyboardButton("⏱️ تایم‌فریم",callback_data="timeframes"),InlineKeyboardButton("⚙️ اهرم Paper",callback_data="leverage")],
        [InlineKeyboardButton("🛡️ ریسک و ایمنی",callback_data="risk"),InlineKeyboardButton("📋 گزارش‌ها",callback_data="reports")],
        [InlineKeyboardButton("🔌 سلامت/اتصال",callback_data="health"),InlineKeyboardButton("⚙️ تنظیمات",callback_data="settings")],
        [InlineKeyboardButton("🔄 Refresh",callback_data="refresh"),InlineKeyboardButton("❓ راهنما",callback_data="help")]
    ])
def symbols_kb(prefix="sig"):
    rows=[]
    for i in range(0,len(SYMBOLS),2): rows.append([InlineKeyboardButton(s,callback_data=f"{prefix}:{s}") for s in SYMBOLS[i:i+2]])
    rows.append([InlineKeyboardButton("🏠 خانه",callback_data="home")]); return InlineKeyboardMarkup(rows)
def timeframes_kb(symbol=None):
    symbol=symbol or DEFAULT_SYMBOL; rows=[]
    for i in range(0,len(TIMEFRAME_KEYS),3): rows.append([InlineKeyboardButton(tf,callback_data=f"tf:{tf}:{symbol}") for tf in TIMEFRAME_KEYS[i:i+3]])
    rows.append([InlineKeyboardButton("⬅️ نمادها",callback_data="signal"),InlineKeyboardButton("🏠 خانه",callback_data="home")]); return InlineKeyboardMarkup(rows)
def leverage_kb(symbol=DEFAULT_SYMBOL,tf="15m"):
    rows=[]
    for i in range(0,len(PAPER_LEVERAGES),3): rows.append([InlineKeyboardButton(f"{x}x",callback_data=f"lev:{x}:{tf}:{symbol}") for x in PAPER_LEVERAGES[i:i+3]])
    rows.append([InlineKeyboardButton("⬅️ تایم‌فریم",callback_data=f"tfmenu:{symbol}"),InlineKeyboardButton("🏠 خانه",callback_data="home")]); return InlineKeyboardMarkup(rows)
def signal_text(s,tf=None,leverage=None):
    decision=s.get("decision","NO TRADE"); label={"LONG":"🟢 LONG","SHORT":"🔴 SHORT","NO TRADE":"🟡 NO TRADE"}.get(decision,decision)
    lines=[f"📊 {s.get('symbol','—')} | {label}",f"قیمت: {fmt(s.get('price'))}",f"امتیاز: {s.get('score','—')} | اعتماد: {s.get('confidence',0)}%"]
    if tf:
        x=s.get("timeframes",{}).get(tf,{})
        lines += [f"⏱️ TF: {tf}",f"TF Score: {x.get('score','—')} | RSI: {fmt(x.get('rsi'),2)} | ATR: {fmt(x.get('atr'))}"]
    if leverage is not None: lines.append(f"📒 Paper leverage: {leverage}x")
    if decision!="NO TRADE":
        lines += [f"Entry: {fmt(s.get('entry'))}",f"🛑 SL: {fmt(s.get('stop'))}",f"🎯 TP1: {fmt(s.get('tp1'))} | R:R {s.get('risk_reward_tp1','—')}",f"🎯 TP2: {fmt(s.get('tp2'))} | R:R {s.get('risk_reward_tp2','—')}",f"🎯 TP3: {fmt(s.get('tp3'))} | R:R {s.get('risk_reward_tp3','—')}"]
    der=s.get("derivatives",{}); lines += [f"Funding: {fmt(der.get('funding_rate'),6)} | OI: {fmt(der.get('open_interest'),2)}",f"دلیل: {s.get('reason','—')}",f"ابطال: {s.get('invalidation','—')}","⚠️ Live execution: DISABLED | Paper only"]
    return "\n".join(lines)
def dashboard_text():
    p=paper_status(); return "🛡️ Trading Guardian\n\nحالت: 📒 PAPER TRADING\n"+f"سرمایه شروع: {fmt(p['balance_start'],2)}\nPnL: {fmt(p['pnl'],2)}\nبسته‌شده: {p['closed']} | Win Rate: {p['win_rate']}%\nProfit Factor: {p['profit_factor']}\nپوزیشن باز: {len(active())}\nKill Switch: {'🔴 فعال' if p['kill_switch'] else '🟢 آماده'}\n\nسفارش واقعی و برداشت وجه فعال نیست."
def paper_text():
    p=paper_status(); rows=["📒 Paper Trading","",f"سرمایه: {fmt(p['balance_start'],2)}",f"PnL: {fmt(p['pnl'],2)}",f"بسته‌شده: {p['closed']} | Win Rate: {p['win_rate']}%",f"Profit Factor: {p['profit_factor']}",f"باز: {len(active())}"]
    for x in active()[:10]: rows.append(f"• {x['id']} | {x['symbol']} {x['side']} | Entry {fmt(x['entry'])} | SL {fmt(x['stop'])} | TP1 {fmt(x['tp1'])}")
    return "\n".join(rows)
def stats_text():
    s=paper_stats(); return "📈 عملکرد Paper\n\n"+f"بسته‌شده: {s['closed']}\nبرد: {s['wins']}\nباخت: {s['losses']}\nWin Rate: {s['win_rate']}%\nProfit Factor: {s['profit_factor']}\nPnL: {fmt(s['pnl'],2)}"
def risk_text():
    p=paper_status(); return "🛡️ ریسک و ایمنی\n\nPAPER ONLY\nسفارش واقعی: خاموش\nبرداشت: خاموش\n"+f"Daily loss limit: {p['daily_loss_limit_pct']}%\nKill Switch: {'🔴 فعال' if p['kill_switch'] else '🟢 آماده'}\nAuto Paper Exit: {'🟢 روشن' if PAPER_AUTO_EXIT else '⚪ خاموش'}\n\nConfidence درصد برد تضمینی نیست؛ نتیجه فقط با Paper Journal سنجیده می‌شود."
def help_text(): return "❓ راهنما\n\n📊 تحلیل جامع = موتور بازار + چندتایم‌فریم + بررسی AI در یک جریان.\n🎯 سیگنال = LONG/SHORT/NO TRADE همراه Entry/SL/TP.\n📒 Paper = شبیه‌سازی، نه سفارش واقعی.\n⚙️ اهرم = فقط سناریوی Paper.\n📋 گزارش‌ها = نتایج و سلامت داده.\n\nLive execution و برداشت وجه در این نسخه فعال نیست."
async def get_signal(symbol): return await asyncio.to_thread(get_signal_snapshot,symbol)
async def get_signal_timeout(symbol,timeout=30): return await asyncio.wait_for(get_signal(symbol),timeout=timeout)
async def send_signal(target,symbol,tf=None,leverage=None):
    try:
        s=await get_signal_timeout(symbol); save_event("telegram_signal",s); buttons=[]
        if s.get("decision") in {"LONG","SHORT"} and not daily_risk_halted(): buttons.append(InlineKeyboardButton("📒 ثبت Paper",callback_data=f"paperopen:{symbol}:{tf or '15m'}:{leverage or 1}"))
        buttons += [InlineKeyboardButton("🎯 TP/SL",callback_data=f"targets:{symbol}:{tf or '15m'}"),InlineKeyboardButton("🔄 دوباره",callback_data=f"sig:{symbol}")]
        await target.reply_text(signal_text(s,tf,leverage),reply_markup=InlineKeyboardMarkup([buttons,[InlineKeyboardButton("⏱️ تایم‌فریم",callback_data=f"tfmenu:{symbol}"),InlineKeyboardButton("⚙️ اهرم Paper",callback_data=f"levmenu:{tf or '15m'}:{symbol}")],[InlineKeyboardButton("🏠 خانه",callback_data="home")]]))
    except asyncio.TimeoutError: await target.reply_text("⚠️ تحلیل بیش از ۳۰ ثانیه طول کشید؛ عملیات متوقف شد.",reply_markup=home_kb())
    except Exception as e: save_event("telegram_error",{"where":"send_signal","error":str(e)}); await target.reply_text(f"⚠️ خطای تحلیل: {type(e).__name__}: {e}",reply_markup=home_kb())
async def ai_review(target,symbol=DEFAULT_SYMBOL):
    if not client: return await target.reply_text("⚠️ OPENAI_API_KEY در محیط ربات قابل خواندن نیست.",reply_markup=home_kb())
    await target.chat.send_action(ChatAction.TYPING)
    try:
        s=await get_signal_timeout(symbol,25); result=await asyncio.wait_for(asyncio.to_thread(review_with_ai,client,s),timeout=30); save_event("review",{"snapshot":s,"result":result}); await target.reply_text("🧠 AI Review\n\n"+result[:4000],reply_markup=home_kb())
    except asyncio.TimeoutError: await target.reply_text("⚠️ زمان بررسی تمام شد. اتصال داده بازار یا AI پاسخ نداد.",reply_markup=home_kb())
    except Exception as e: save_event("telegram_error",{"where":"ai_review","error":str(e)}); await target.reply_text(f"⚠️ خطای AI: {type(e).__name__}: {e}",reply_markup=home_kb())
async def comprehensive(target):
    if not client: return await target.reply_text("⚠️ OPENAI_API_KEY در محیط ربات قابل خواندن نیست.",reply_markup=home_kb())
    await target.chat.send_action(ChatAction.TYPING)
    try:
        s=await get_signal_timeout(DEFAULT_SYMBOL,25); ai=await asyncio.wait_for(asyncio.to_thread(review_with_ai,client,s),timeout=30); save_event("comprehensive_analysis",{"snapshot":s,"ai":ai}); await target.reply_text("📊 تحلیل جامع\n\n"+signal_text(s)+"\n\n🧠 نظر مستقل AI:\n"+ai[:3000],reply_markup=home_kb())
    except asyncio.TimeoutError: await target.reply_text("⚠️ تحلیل جامع به‌موقع پاسخ نداد و متوقف شد.",reply_markup=home_kb())
    except Exception as e: save_event("telegram_error",{"where":"comprehensive","error":str(e)}); await target.reply_text(f"⚠️ خطای تحلیل جامع: {type(e).__name__}: {e}",reply_markup=home_kb())
async def callback(update,context):
    q=update.callback_query
    if not auth(update): return await q.answer()
    await q.answer(); d=q.data
    try:
        if d in {"home","dashboard"}: return await q.edit_message_text(dashboard_text(),reply_markup=home_kb())
        if d=="analysis": return await comprehensive(q.message)
        if d in {"markets","signal"}: return await q.edit_message_text("🎯 نماد را انتخاب کن:",reply_markup=symbols_kb())
        if d=="timeframes": return await q.edit_message_text("⏱️ تایم‌فریم را انتخاب کن:",reply_markup=timeframes_kb())
        if d.startswith("tfmenu:"): return await q.edit_message_text("⏱️ تایم‌فریم را انتخاب کن:",reply_markup=timeframes_kb(d.split(":",1)[1]))
        if d=="leverage": return await q.edit_message_text("⚙️ اهرم سناریوی Paper:",reply_markup=leverage_kb())
        if d.startswith("levmenu:"):
            _,tf,symbol=d.split(":",2); return await q.edit_message_text(f"⚙️ Paper leverage | {symbol} | {tf}",reply_markup=leverage_kb(symbol,tf))
        if d.startswith("lev:"):
            _,lev,tf,symbol=d.split(":",3); return await send_signal(q.message,symbol,tf,int(lev))
        if d=="review": return await ai_review(q.message)
        if d=="stats": return await q.edit_message_text(stats_text(),reply_markup=home_kb())
        if d=="paper": return await q.edit_message_text(paper_text(),reply_markup=home_kb())
        if d=="risk": return await q.edit_message_text(risk_text(),reply_markup=home_kb())
        if d=="health": return await q.edit_message_text("🔌 سلامت سرویس\n\n🟢 Bot process: OK\n🟢 Paper engine: available\n"+f"{'🟢 OpenAI key loaded' if client else '🔴 OpenAI key missing'}\n🟢 Live orders: DISABLED\n🟢 Withdrawals: DISABLED",reply_markup=home_kb())
        if d=="settings": return await q.edit_message_text(f"⚙️ تنظیمات\n\nنماد پیش‌فرض: {DEFAULT_SYMBOL}\nمدل AI: {OPENAI_MODEL}\nMonitor: {MONITOR_INTERVAL}s\nPaper Auto Exit: {PAPER_AUTO_EXIT}",reply_markup=home_kb())
        if d=="reports":
            s=paper_stats(); return await q.edit_message_text("📋 گزارش‌ها\n\n"+f"Paper closed: {s['closed']}\nWin rate: {s['win_rate']}%\nPnL: {fmt(s['pnl'],2)}\nثبت رویدادها در data/journal.jsonl انجام می‌شود.",reply_markup=home_kb())
        if d=="refresh": return await send_signal(q.message,DEFAULT_SYMBOL)
        if d.startswith("sig:"): return await send_signal(q.message,d.split(":",1)[1])
        if d.startswith("tf:"):
            _,tf,symbol=d.split(":",2); return await send_signal(q.message,symbol,tf,1)
        if d.startswith("targets:"):
            _,symbol,tf=d.split(":",2); s=await get_signal_timeout(symbol,25); return await q.edit_message_text("🎯 TP/SL\n\n"+signal_text(s,tf),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📒 ثبت Paper",callback_data=f"paperopen:{symbol}:{tf}:1")],[InlineKeyboardButton("🔄 دوباره",callback_data=f"sig:{symbol}"),InlineKeyboardButton("🏠 خانه",callback_data="home")]]))
        if d.startswith("paperopen:"):
            _,symbol,tf,lev=d.split(":",3); s=await get_signal_timeout(symbol,25); result=await asyncio.to_thread(paper_open,s,1.0); save_event("paper_parameters",{"symbol":symbol,"timeframe":tf,"leverage":int(lev),"signal_id":s.get("signal_id"),"paper_result":result}); text=("✅ در Paper ثبت شد.\n" if result.get("ok") else "⚠️ ثبت نشد: ")+str(result.get("trade") if result.get("ok") else result.get("reason","—")); return await q.message.reply_text(text+f"\n⏱️ TF: {tf}\n⚙️ Leverage scenario: {lev}x",reply_markup=home_kb())
    except asyncio.TimeoutError: await q.message.reply_text("⚠️ عملیات بیش از حد طول کشید و متوقف شد.",reply_markup=home_kb())
    except Exception as e: save_event("telegram_error",{"where":"callback","data":d,"error":str(e)}); await q.message.reply_text(f"⚠️ خطای دکمه: {type(e).__name__}: {e}",reply_markup=home_kb())
async def start(update,context):
    if auth(update): await update.message.reply_text("🛡️ Trading Guardian آماده است.\nحالت: PAPER TRADING",reply_markup=home_kb())
async def command_signal(update,context):
    if auth(update): await update.message.reply_text("🎯 نماد را انتخاب کن:",reply_markup=symbols_kb())
async def command_help(update,context):
    if auth(update): await update.message.reply_text(help_text(),reply_markup=home_kb())
async def command_health(update,context):
    if auth(update): await update.message.reply_text("🟢 Bot process: OK\n🟢 Paper engine: available\n🟢 Live orders: DISABLED",reply_markup=home_kb())
async def monitor(app):
    if not MONITOR_CHAT_ID:return
    last={}
    while True:
        try:
            for symbol in SYMBOLS:
                s=await get_signal_timeout(symbol,25); sig=(symbol,s.get("decision"),s.get("entry"),s.get("stop"),s.get("tp1"))
                if s.get("decision")!="NO TRADE" and sig!=last.get(symbol): await app.bot.send_message(chat_id=MONITOR_CHAT_ID,text=signal_text(s),reply_markup=home_kb()); last[symbol]=sig
                if PAPER_AUTO_EXIT:
                    for t in active():
                        if t.get("symbol")!=symbol or s.get("price") is None:continue
                        price=float(s["price"]); side=t.get("side"); stop=float(t["stop"]); tp=float(t["tp1"]); hit=(side=="LONG" and (price<=stop or price>=tp)) or (side=="SHORT" and (price>=stop or price<=tp))
                        if hit:
                            reason="SL" if (side=="LONG" and price<=stop) or (side=="SHORT" and price>=stop) else "TP1"; c=await asyncio.to_thread(paper_close,t,price,reason); await app.bot.send_message(chat_id=MONITOR_CHAT_ID,text=f"📒 Paper {reason}\n{symbol} {side}\nExit: {fmt(c['exit'])}\nPnL: {fmt(c['pnl'],4)}")
                save_event("monitor_tick",s)
        except Exception as e: save_event("monitor_error",{"error":str(e)})
        await asyncio.sleep(MONITOR_INTERVAL)
async def post_init(app): app.create_task(monitor(app),name="market-monitor")
def main():
    app=Application.builder().token(TOKEN).post_init(post_init).build(); app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("signal",command_signal)); app.add_handler(CommandHandler("help",command_help)); app.add_handler(CommandHandler("health",command_health)); app.add_handler(CallbackQueryHandler(callback)); app.run_polling(drop_pending_updates=True)
if __name__=="__main__": main()
