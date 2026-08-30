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
ALLOWED={x.strip() for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS","").split(",") if x.strip()}
MONITOR_CHAT_ID=os.getenv("TELEGRAM_MONITOR_CHAT_ID","").strip()
MONITOR_INTERVAL=max(30,int(os.getenv("MONITOR_INTERVAL_SECONDS","60")))
PAPER_AUTO_EXIT=os.getenv("PAPER_AUTO_EXIT","true").lower() in {"1","true","yes","on"}
client=OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
if not TOKEN or any(ord(c)<32 or ord(c)>126 or c.isspace() for c in TOKEN): raise RuntimeError("TELEGRAM_BOT_TOKEN is missing or invalid")

TIMEFRAME_KEYS=tuple(TIMEFRAMES.keys())
PAPER_LEVERAGES=(1,2,3,5,10,20)

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
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 داشبورد",callback_data="dashboard"),InlineKeyboardButton("📡 بازار",callback_data="markets")],
        [InlineKeyboardButton("🟢 سیگنال",callback_data="signal"),InlineKeyboardButton("🧠 AI Review",callback_data="review")],
        [InlineKeyboardButton("📒 Paper",callback_data="paper"),InlineKeyboardButton("📈 عملکرد",callback_data="stats")],
        [InlineKeyboardButton("⏱️ تایم‌فریم",callback_data="timeframes"),InlineKeyboardButton("⚙️ Paper Leverage",callback_data="leverage")],
        [InlineKeyboardButton("🔄 بروزرسانی",callback_data="refresh"),InlineKeyboardButton("🛡️ ایمنی",callback_data="safety")],
        [InlineKeyboardButton("⚙️ تنظیمات",callback_data="settings"),InlineKeyboardButton("❓ راهنما",callback_data="help")]
    ])
def symbol_kb():
    rows=[]
    for i in range(0,len(SYMBOLS),2): rows.append([InlineKeyboardButton(s,callback_data=f"sig:{s}") for s in SYMBOLS[i:i+2]])
    rows.append([InlineKeyboardButton("⏱️ انتخاب تایم‌فریم",callback_data="timeframes")])
    rows.append([InlineKeyboardButton("⬅️ خانه",callback_data="home")])
    return InlineKeyboardMarkup(rows)
def timeframe_kb(symbol=None):
    rows=[]
    for i in range(0,len(TIMEFRAME_KEYS),3):
        rows.append([InlineKeyboardButton(tf,callback_data=f"tf:{tf}:{symbol or os.getenv('SYMBOL',SYMBOLS[0])}") for tf in TIMEFRAME_KEYS[i:i+3]])
    rows.append([InlineKeyboardButton("⬅️ نمادها",callback_data="signal"),InlineKeyboardButton("🏠 خانه",callback_data="home")])
    return InlineKeyboardMarkup(rows)
def leverage_kb(symbol,tf):
    rows=[]
    for i in range(0,len(PAPER_LEVERAGES),3):
        rows.append([InlineKeyboardButton(f"{x}x",callback_data=f"lev:{x}:{tf}:{symbol}") for x in PAPER_LEVERAGES[i:i+3]])
    rows.append([InlineKeyboardButton("1x بدون اهرم",callback_data=f"lev:1:{tf}:{symbol}")])
    rows.append([InlineKeyboardButton("⬅️ تایم‌فریم",callback_data=f"tfmenu:{symbol}"),InlineKeyboardButton("🏠 خانه",callback_data="home")])
    return InlineKeyboardMarkup(rows)
def signal_text(s,selected_tf=None,leverage=None):
    d=s.get("decision","NO TRADE"); label={"LONG":"🟢 LONG","SHORT":"🔴 SHORT","NO TRADE":"🟡 NO TRADE"}.get(d,d)
    a=[f"📊 Trading Guardian | {s.get('symbol','—')}",f"تصمیم: {label}",f"قیمت: {fmt(s.get('price'))}",f"امتیاز: {s.get('score','—')}",f"اطمینان مدل: {s.get('confidence',0)}%"]
    if selected_tf:
        x=s.get("timeframes",{}).get(selected_tf,{})
        a += [f"⏱️ تایم‌فریم انتخابی: {selected_tf}",f"TF Score: {x.get('score','—')} | RSI: {fmt(x.get('rsi'),2)} | ATR: {fmt(x.get('atr'))}"]
    if leverage is not None:a.append(f"📒 Paper Leverage: {leverage}x")
    if d!="NO TRADE":
        a += [f"Entry: {fmt(s.get('entry'))}",f"🛑 SL: {fmt(s.get('stop'))}",f"🎯 TP1: {fmt(s.get('tp1'))} | R:R {s.get('risk_reward_tp1','—')}",f"🎯 TP2: {fmt(s.get('tp2'))} | R:R {s.get('risk_reward_tp2','—')}",f"🎯 TP3: {fmt(s.get('tp3'))} | R:R {s.get('risk_reward_tp3','—')}"]
    der=s.get("derivatives",{}); a += [f"Funding: {fmt(der.get('funding_rate'),6)} | OI: {fmt(der.get('open_interest'),2)}",f"دلیل: {s.get('reason','—')}",f"ابطال: {s.get('invalidation','—')}","⚠️ حالت فعلی: فقط Paper؛ سفارش واقعی فعال نیست."]
    return "\n".join(a)
def target_result_text(s):
    p=paper_stats(); d=s.get("decision","NO TRADE")
    return (f"🎯 نتیجه/وضعیت تارگت {s.get('symbol','—')}\n\n"
            f"سیگنال: {d}\nاعتماد مدل: {s.get('confidence',0)}%\n"
            f"Entry: {fmt(s.get('entry'))}\nSL: {fmt(s.get('stop'))}\n"
            f"TP1: {fmt(s.get('tp1'))}\nTP2: {fmt(s.get('tp2'))}\nTP3: {fmt(s.get('tp3'))}\n\n"
            f"📊 نتیجه تاریخی Paper ربات: {p['closed']} بسته | Win Rate: {p['win_rate']}% | PnL: {fmt(p['pnl'],2)}\n"
            "درصد اعتماد مدل، درصد برد تضمینی نیست؛ نتیجه تارگت فقط با Paper Trading قابل سنجش است.")
def dashboard():
    p=paper_status(); return "🛡️ Trading Guardian\n\nحالت: 📒 PAPER TRADING\n"+f"سرمایه شروع: {fmt(p['balance_start'],2)}\nPnL: {fmt(p['pnl'],2)}\nمعاملات بسته: {p['closed']} | Win Rate: {p['win_rate']}%\nProfit Factor: {p['profit_factor']}\nپوزیشن باز: {len(active())}\nKill Switch: {'🔴 فعال' if p['kill_switch'] else '🟢 آماده'}\n\nسفارش واقعی و برداشت وجه فعال نیست."
def paper_text():
    p=paper_status(); a=active(); t="📒 Paper Trading\n\n"+f"سرمایه: {fmt(p['balance_start'],2)}\nPnL: {fmt(p['pnl'],2)}\nبسته‌شده: {p['closed']} | Win Rate: {p['win_rate']}%\nProfit Factor: {p['profit_factor']}\nباز: {len(a)}\n"
    if a:t+="\n"+"\n".join(f"• {x['id']} | {x['symbol']} {x['side']} | Entry {fmt(x['entry'])} | SL {fmt(x['stop'])} | TP1 {fmt(x['tp1'])}" for x in a[:10])
    return t
def stats_text():
    s=paper_stats(); return "📈 عملکرد Paper\n\n"+f"بسته‌شده: {s['closed']}\nبرد: {s['wins']}\nباخت: {s['losses']}\nWin Rate: {s['win_rate']}%\nProfit Factor: {s['profit_factor']}\nPnL: {fmt(s['pnl'],2)}"
def help_text():return "❓ راهنما\n\n/start — منوی اصلی\n/signal — انتخاب نماد و تحلیل\n/stats — عملکرد\n/paper — Paper\n/health — سلامت سرویس\n/help — راهنما\n\nتایم‌فریم‌ها: 5m/10m/15m/30m/1h/4h/1d\nاهرم فقط برای سناریوی Paper است.\nحالت Live و سفارش واقعی فعال نیست."
def safety_text():
    p=paper_status(); return "🛡️ ایمنی\n\nPAPER ONLY\nسفارش واقعی: خاموش\nبرداشت: خاموش\n"+f"Daily loss limit: {p['daily_loss_limit_pct']}%\nKill Switch: {'🔴 فعال' if p['kill_switch'] else '🟢 آماده'}\nAuto Paper Exit: {'🟢 روشن' if PAPER_AUTO_EXIT else '⚪ خاموش'}"
async def get_signal(symbol): return await asyncio.to_thread(get_signal_snapshot,symbol)
async def send_signal(target,symbol,selected_tf=None,leverage=None):
    try:
        s=await get_signal(symbol); save_event("telegram_signal",s); b=[]
        if s.get("decision") in {"LONG","SHORT"} and not daily_risk_halted():
            b.append(InlineKeyboardButton("📒 ثبت Paper",callback_data=f"paperopen:{symbol}:{selected_tf or '15m'}:{leverage or 1}"))
        b += [InlineKeyboardButton("🎯 نتیجه تارگت",callback_data=f"result:{symbol}:{selected_tf or '15m'}"),InlineKeyboardButton("🔄 دوباره",callback_data=f"sig:{symbol}")]
        b2=[InlineKeyboardButton("⏱️ تایم‌فریم",callback_data=f"tfmenu:{symbol}"),InlineKeyboardButton("⚙️ اهرم Paper",callback_data=f"levmenu:{selected_tf or '15m'}:{symbol}")]
        b3=[InlineKeyboardButton("🏠 خانه",callback_data="home")]
        await target.reply_text(signal_text(s,selected_tf,leverage),reply_markup=InlineKeyboardMarkup([b,b2,b3]))
    except Exception as e: await target.reply_text(f"⚠️ خطا: {e}",reply_markup=main_kb())
async def start(update,context):
    if auth(update):await update.message.reply_text("🛡️ Trading Guardian آماده است.\nحالت: PAPER TRADING",reply_markup=main_kb())
async def command_signal(update,context):
    if auth(update):await update.message.reply_text("🟢 نماد را انتخاب کن:",reply_markup=symbol_kb())
async def command_stats(update,context):
    if auth(update):await update.message.reply_text(stats_text(),reply_markup=main_kb())
async def command_paper(update,context):
    if auth(update):await update.message.reply_text(paper_text(),reply_markup=main_kb())
async def health(update,context):
    if auth(update):await update.message.reply_text("🟢 Bot process: OK\n🟢 Paper engine: available\n🟢 Live orders: DISABLED\n🟢 Withdrawals: DISABLED",reply_markup=main_kb())
async def command_help(update,context):
    if auth(update):await update.message.reply_text(help_text(),reply_markup=main_kb())
async def callback(update,context):
    q=update.callback_query
    if not auth(update):return await q.answer()
    await q.answer(); d=q.data
    if d in {"home","dashboard"}:return await q.edit_message_text(dashboard(),reply_markup=main_kb())
    if d=="markets":return await q.edit_message_text("📡 بازارهای فعال\n\n"+"\n".join(f"• {s}" for s in SYMBOLS),reply_markup=symbol_kb())
    if d=="signal":return await q.edit_message_text("🟢 نماد را انتخاب کن:",reply_markup=symbol_kb())
    if d=="timeframes":return await q.edit_message_text("⏱️ تایم‌فریم تحلیل را انتخاب کن:\n\nتحلیل موتور همچنان چندتایم‌فریمی است؛ این انتخاب فقط نمای تایم‌فریم و نتیجه آن را مشخص می‌کند.",reply_markup=timeframe_kb())
    if d.startswith("tfmenu:"):
        symbol=d.split(":",1)[1]; return await q.edit_message_text(f"⏱️ {symbol} — تایم‌فریم را انتخاب کن:",reply_markup=timeframe_kb(symbol))
    if d=="leverage":return await q.edit_message_text("⚙️ اهرم سناریوی Paper را انتخاب کن:",reply_markup=leverage_kb(os.getenv("SYMBOL",SYMBOLS[0]),"15m"))
    if d.startswith("levmenu:"):
        _,tf,symbol=d.split(":",2); return await q.edit_message_text(f"⚙️ اهرم Paper | {symbol} | {tf}\n\nاین مقدار فقط در سناریوی شبیه‌سازی استفاده می‌شود.",reply_markup=leverage_kb(symbol,tf))
    if d=="stats":return await q.edit_message_text(stats_text(),reply_markup=main_kb())
    if d=="paper":return await q.edit_message_text(paper_text(),reply_markup=main_kb())
    if d=="safety":return await q.edit_message_text(safety_text(),reply_markup=main_kb())
    if d=="help":return await q.edit_message_text(help_text(),reply_markup=main_kb())
    if d=="settings":return await q.edit_message_text("⚙️ تنظیمات\n\nنماد پیش‌فرض: "+os.getenv("SYMBOL","BTCUSDT")+f"\nبازه مانیتور: {MONITOR_INTERVAL} ثانیه\nAuto Paper Exit: {PAPER_AUTO_EXIT}",reply_markup=main_kb())
    if d=="refresh":return await send_signal(q.message,os.getenv("SYMBOL",SYMBOLS[0]))
    if d=="review":
        if not client:return await q.edit_message_text("⚠️ OPENAI_API_KEY تنظیم نشده است.",reply_markup=main_kb())
        await q.edit_message_text("🧠 در حال بررسی...",reply_markup=main_kb()); await q.message.chat.send_action(ChatAction.TYPING)
        try:
            s=await get_signal(os.getenv("SYMBOL",SYMBOLS[0])); r=await asyncio.to_thread(review_with_ai,client,s); save_event("review",{"snapshot":s,"result":r}); await q.message.reply_text(r[:4000],reply_markup=main_kb())
        except Exception as e:await q.message.reply_text(f"⚠️ خطای AI: {e}",reply_markup=main_kb())
        return
    if d.startswith("sig:"):return await send_signal(q.message,d.split(":",1)[1])
    if d.startswith("tf:"):
        _,tf,symbol=d.split(":",2); return await send_signal(q.message,symbol,tf,1)
    if d.startswith("lev:"):
        _,lev,tf,symbol=d.split(":",3); return await send_signal(q.message,symbol,tf,int(lev))
    if d.startswith("result:"):
        _,symbol,tf=d.split(":",2); s=await get_signal(symbol); return await q.edit_message_text(target_result_text(s),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📒 Paper",callback_data=f"paperopen:{symbol}:{tf}:1")],[InlineKeyboardButton("🔄 دوباره",callback_data=f"sig:{symbol}"),InlineKeyboardButton("🏠 خانه",callback_data="home")]]))
    if d.startswith("paperopen:"):
        _,symbol,tf,lev=d.split(":",3); s=await get_signal(symbol); r=await asyncio.to_thread(paper_open,s,1.0); save_event("paper_parameters",{"symbol":symbol,"timeframe":tf,"leverage":int(lev),"signal_id":s.get("signal_id"),"paper_result":r}); return await q.message.reply_text(("✅ در Paper ثبت شد.\n" if r.get("ok") else "⚠️ ثبت نشد: ")+str(r.get("trade") if r.get("ok") else r.get("reason","—"))+f"\n⏱️ TF: {tf}\n⚙️ Leverage scenario: {lev}x",reply_markup=main_kb())
async def monitor(app):
    if not MONITOR_CHAT_ID:return
    last={}
    while True:
        try:
            for symbol in SYMBOLS:
                s=await get_signal(symbol); sig=(symbol,s.get("decision"),s.get("entry"),s.get("stop"),s.get("tp1"),s.get("tp2"),s.get("tp3"))
                if s.get("decision")!="NO TRADE" and sig!=last.get(symbol):await app.bot.send_message(chat_id=MONITOR_CHAT_ID,text=signal_text(s),reply_markup=main_kb()); last[symbol]=sig
                if PAPER_AUTO_EXIT:
                    for t in active():
                        if t.get("symbol")!=symbol or s.get("price") is None:continue
                        price=float(s["price"]); side=t.get("side"); stop=float(t["stop"]); tp=float(t["tp1"])
                        hit=(side=="LONG" and (price<=stop or price>=tp)) or (side=="SHORT" and (price>=stop or price<=tp))
                        if hit:
                            reason="SL" if (side=="LONG" and price<=stop) or (side=="SHORT" and price>=stop) else "TP1"; c=await asyncio.to_thread(paper_close,t,price,reason); await app.bot.send_message(chat_id=MONITOR_CHAT_ID,text=f"📒 Paper {reason}\n{symbol} {side}\nExit: {fmt(c['exit'])}\nPnL: {fmt(c['pnl'],4)}")
                save_event("monitor_tick",s)
        except Exception as e:save_event("monitor_error",{"error":str(e)})
        await asyncio.sleep(MONITOR_INTERVAL)
async def post_init(app):app.create_task(monitor(app),name="market-monitor")
def main():
    app=Application.builder().token(TOKEN).post_init(post_init).build()
    for cmd,fn in (("start",start),("signal",command_signal),("stats",command_stats),("paper",command_paper),("health",health),("help",command_help)):app.add_handler(CommandHandler(cmd,fn))
    app.add_handler(CallbackQueryHandler(callback)); app.run_polling(drop_pending_updates=True)
if __name__=="__main__":main()
