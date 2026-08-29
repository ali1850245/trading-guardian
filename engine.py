import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

DATA = Path(os.getenv("DATA_DIR", "data")); DATA.mkdir(parents=True, exist_ok=True)
JOURNAL = DATA / "journal.jsonl"; PAPER_JOURNAL = DATA / "paper_trades.jsonl"
WALLEX = os.getenv("WALLEX_BASE_URL", "https://api.wallex.ir")
BINANCE = os.getenv("BINANCE_BASE_URL", "https://api.binance.com")
FUTURES = os.getenv("BINANCE_FUTURES_URL", "https://fapi.binance.com")
DEFAULT_SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
SYMBOLS = tuple(x.strip().upper() for x in os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT").split(",") if x.strip())
TIMEFRAMES = {"5m":{"resolution":"5","minutes":5,"weight":1,"role":"trigger"},"10m":{"resolution":"10","minutes":10,"weight":2,"role":"trigger"},"15m":{"resolution":"15","minutes":15,"weight":2,"role":"setup"},"30m":{"resolution":"30","minutes":30,"weight":3,"role":"setup"},"1h":{"resolution":"60","minutes":60,"weight":4,"role":"structure"},"4h":{"resolution":"240","minutes":240,"weight":5,"role":"structure"},"1d":{"resolution":"1D","minutes":1440,"weight":6,"role":"macro"}}
WEIGHTS = {k:v["weight"] for k,v in TIMEFRAMES.items()}
MIN_CANDLES=int(os.getenv("MIN_CANDLES","220")); MAX_SPREAD_PCT=float(os.getenv("MAX_SPREAD_PCT","0.50")); PAPER_START_BALANCE=float(os.getenv("PAPER_START_BALANCE","10000")); DAILY_LOSS_LIMIT_PCT=float(os.getenv("DAILY_LOSS_LIMIT_PCT","3")); TIMEOUT=int(os.getenv("REQUEST_TIMEOUT","15"))

def now_utc(): return datetime.now(timezone.utc).isoformat()
def save_event(event,payload):
    with JOURNAL.open("a",encoding="utf-8") as f:f.write(json.dumps({"ts":now_utc(),"event":event,"payload":payload},ensure_ascii=False)+"\n")
def safe_float(v,default=0.0):
    try:
        if v is None or v=="": return default
        v=float(v); return v if np.isfinite(v) else default
    except (TypeError,ValueError): return default

def api_get(base,path,params=None,retries=3):
    err=None
    for i in range(retries):
        try:
            r=requests.get(base+path,params=params or {},timeout=TIMEOUT,headers={"User-Agent":"TradingGuardian/5.0","Accept":"application/json"}); r.raise_for_status(); d=r.json()
            if not isinstance(d,(dict,list)): raise RuntimeError("Invalid API response")
            return d
        except Exception as e:
            err=e
            if i<retries-1: time.sleep(i+1)
    raise RuntimeError(f"API request failed: {err}")

def wallex_snapshot(symbol=DEFAULT_SYMBOL):
    try:
        d=api_get(WALLEX,"/v1/markets"); item=d.get("result",{}).get("symbols",{}).get(symbol)
        if not item:return {"symbol":symbol,"error":f"Market {symbol} was not found on Wallex","source":"wallex"}
        s=item.get("stats",{}); bid,ask=safe_float(s.get("bidPrice")),safe_float(s.get("askPrice")); last=safe_float(s.get("lastPrice")) or ((bid+ask)/2 if bid and ask else 0)
        return {"symbol":symbol,"bid":bid,"ask":ask,"last":last,"volume24h":safe_float(s.get("24h_volume")),"quoteVolume24h":safe_float(s.get("24h_quoteVolume")),"change24h":safe_float(s.get("24h_ch")),"change7d":safe_float(s.get("7d_ch")),"high24h":safe_float(s.get("24h_highPrice")),"low24h":safe_float(s.get("24h_lowPrice")),"source":"wallex","received_at":now_utc()}
    except Exception as e:return {"symbol":symbol,"error":str(e),"source":"wallex"}
def binance_snapshot(symbol=DEFAULT_SYMBOL):
    try:
        d=api_get(BINANCE,"/api/v3/ticker/24hr",{"symbol":symbol}); return {"symbol":symbol,"bid":safe_float(d.get("bidPrice")),"ask":safe_float(d.get("askPrice")),"last":safe_float(d.get("lastPrice")),"volume24h":safe_float(d.get("volume")),"quoteVolume24h":safe_float(d.get("quoteVolume")),"change24h":safe_float(d.get("priceChangePercent")),"high24h":safe_float(d.get("highPrice")),"low24h":safe_float(d.get("lowPrice")),"source":"binance","received_at":now_utc()}
    except Exception as e:return {"symbol":symbol,"error":str(e),"source":"binance"}
def market_snapshot(symbol=DEFAULT_SYMBOL):
    w=wallex_snapshot(symbol); return w if not w.get("error") and w.get("last") else binance_snapshot(symbol)

def orderbook_snapshot(symbol=DEFAULT_SYMBOL):
    try:
        try:
            r=api_get(WALLEX,"/v1/depth",{"symbol":symbol}).get("result",{}); bids,asks=r.get("bid",[]),r.get("ask",[])
            if bids and asks:
                bn=sum(safe_float(x.get("sum")) for x in bids[:20]); an=sum(safe_float(x.get("sum")) for x in asks[:20]); bb,ba=safe_float(bids[0].get("price")),safe_float(asks[0].get("price")); total=bn+an; mid=(bb+ba)/2; sp=ba-bb
                return {"bid_notional_top20":bn,"ask_notional_top20":an,"imbalance":(bn-an)/total if total else 0,"best_bid":bb,"best_ask":ba,"spread":sp,"spread_pct":sp/mid*100 if mid else 0,"source":"wallex"}
        except Exception: pass
        d=api_get(BINANCE,"/api/v3/depth",{"symbol":symbol,"limit":20}); bids,asks=d.get("bids",[]),d.get("asks",[])
        if not bids or not asks:raise RuntimeError("Order book is empty")
        bn=sum(safe_float(x[0])*safe_float(x[1]) for x in bids); an=sum(safe_float(x[0])*safe_float(x[1]) for x in asks); bb,ba=safe_float(bids[0][0]),safe_float(asks[0][0]); total=bn+an; mid=(bb+ba)/2; sp=ba-bb
        return {"bid_notional_top20":bn,"ask_notional_top20":an,"imbalance":(bn-an)/total if total else 0,"best_bid":bb,"best_ask":ba,"spread":sp,"spread_pct":sp/mid*100 if mid else 0,"source":"binance"}
    except Exception as e:return {"error":str(e),"imbalance":0,"spread_pct":999}
def recent_trades(symbol=DEFAULT_SYMBOL):
    try:
        d=api_get(BINANCE,"/api/v3/trades",{"symbol":symbol,"limit":100}); buy=sum(safe_float(x.get("qty")) for x in d if not x.get("isBuyerMaker")); sell=sum(safe_float(x.get("qty")) for x in d if x.get("isBuyerMaker")); total=buy+sell
        return {"trade_count":len(d),"buy_volume":buy,"sell_volume":sell,"buy_ratio":buy/total if total else .5,"source":"binance"}
    except Exception as e:return {"error":str(e),"buy_ratio":.5}
def _clean_binance(rows):
    f=pd.DataFrame(rows,columns=["timestamp","open","high","low","close","volume","close_time","quote_volume","trades","taker_base","taker_quote","ignore"]); f["timestamp"]=pd.to_numeric(f["timestamp"],errors="coerce")//1000
    for c in ["open","high","low","close","volume"]:f[c]=pd.to_numeric(f[c],errors="coerce")
    return f[["timestamp","open","high","low","close","volume"]].replace([np.inf,-np.inf],np.nan).dropna().drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
def get_candles(symbol=DEFAULT_SYMBOL,resolution="15",limit=300):
    resolution=str(resolution); interval={"5":"5m","10":"10m","15":"15m","30":"30m","60":"1h","240":"4h","1D":"1d"}.get(resolution); fetch_limit=min(max(limit,MIN_CANDLES),1000); primary_error=None
    try:
        if not interval:raise RuntimeError(f"Unsupported native interval: {resolution}")
        frame=_clean_binance(api_get(BINANCE,"/api/v3/klines",{"symbol":symbol,"interval":interval,"limit":fetch_limit}));
        if len(frame)<MIN_CANDLES:raise RuntimeError(f"Not enough candles: {len(frame)}")
        if len(frame)>1:frame=frame.iloc[:-1].reset_index(drop=True)
        if len(frame)<MIN_CANDLES:raise RuntimeError("Not enough closed candles")
        return frame.tail(limit).reset_index(drop=True)
    except Exception as e:primary_error=e
    try:
        wallex_res="D" if resolution=="1D" else resolution; minutes=TIMEFRAMES.get(resolution,{}).get("minutes",15); end=int(time.time()); start=end-minutes*60*fetch_limit; d=api_get(WALLEX,"/v1/udf/history",{"symbol":symbol,"resolution":wallex_res,"from":start,"to":end})
        if d.get("s")!="ok":raise RuntimeError(str(d))
        keys=["t","o","h","l","c","v"]; n=min(len(d.get(k,[])) for k in keys)
        if n<MIN_CANDLES:raise RuntimeError(f"Not enough Wallex candles: {n}")
        frame=pd.DataFrame({"timestamp":d["t"][:n],"open":d["o"][:n],"high":d["h"][:n],"low":d["l"][:n],"close":d["c"][:n],"volume":d["v"][:n]})
        for c in ["open","high","low","close","volume"]:frame[c]=pd.to_numeric(frame[c],errors="coerce")
        frame=frame.replace([np.inf,-np.inf],np.nan).dropna().drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
        if len(frame)>1:frame=frame.iloc[:-1].reset_index(drop=True)
        if len(frame)<MIN_CANDLES:raise RuntimeError("Not enough closed Wallex candles")
        return frame.tail(limit).reset_index(drop=True)
    except Exception as e:raise RuntimeError(f"Candle retrieval failed for {resolution}; primary={primary_error}; fallback={e}")
def wallex_candles(symbol=DEFAULT_SYMBOL,resolution="15",limit=300):return get_candles(symbol,resolution,limit)
def derivatives_snapshot(symbol=DEFAULT_SYMBOL):
    out={"source":"binance_futures","funding_rate":None,"open_interest":None,"liquidations_5m":None}
    try:out["funding_rate"]=safe_float(api_get(FUTURES,"/fapi/v1/premiumIndex",{"symbol":symbol}).get("lastFundingRate"),None)
    except Exception as e:out["funding_error"]=str(e)
    try:out["open_interest"]=safe_float(api_get(FUTURES,"/fapi/v1/openInterest",{"symbol":symbol}).get("openInterest"),None)
    except Exception as e:out["oi_error"]=str(e)
    return out
def ema(s,p):return s.ewm(span=p,adjust=False).mean()
def rsi(s,p=14):
    d=s.diff(); g=d.clip(lower=0).ewm(alpha=1/p,adjust=False).mean(); l=(-d.clip(upper=0)).ewm(alpha=1/p,adjust=False).mean(); rs=g/l.replace(0,np.nan); return (100-100/(1+rs)).fillna(50)
def atr(df,p=14):
    prev=df.close.shift(1); tr=pd.concat([df.high-df.low,(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1); return tr.ewm(alpha=1/p,adjust=False).mean()
def indicators(df):
    o=df.copy(); o["ema20"],o["ema50"],o["ema200"]=ema(o.close,20),ema(o.close,50),ema(o.close,200); o["rsi"]=rsi(o.close); fast,slow=ema(o.close,12),ema(o.close,26); o["macd"]=fast-slow; o["signal"]=ema(o.macd,9); o["hist"]=o.macd-o.signal; o["atr"]=atr(o); o["volume_ratio"]=o.volume/o.volume.rolling(20).mean().replace(0,np.nan); o["roc10"]=o.close.pct_change(10)*100; o["high20"]=o.high.rolling(20).max(); o["low20"]=o.low.rolling(20).min(); return o
def timeframe_analysis(df):
    x=indicators(df).iloc[-1]; score=0; reasons=[]; bull=bear=0; close,e20,e50,e200=map(safe_float,[x.close,x.ema20,x.ema50,x.ema200]); rv,hist,vr,roc=safe_float(x.rsi,50),safe_float(x.hist),safe_float(x.volume_ratio,1),safe_float(x.roc10)
    if close>e20>e50>e200:score+=4;bull+=1;reasons.append("ساختار روند صعودی")
    elif close<e20<e50<e200:score-=4;bear+=1;reasons.append("ساختار روند نزولی")
    else:reasons.append("روند کاملاً هم‌جهت نیست")
    if e20>e50:score+=1;bull+=1;reasons.append("EMA20 بالاتر از EMA50")
    elif e20<e50:score-=1;bear+=1;reasons.append("EMA20 پایین‌تر از EMA50")
    if 55<=rv<70:score+=2;bull+=1;reasons.append("RSI صعودی بدون اشباع شدید")
    elif 30<rv<=45:score-=2;bear+=1;reasons.append("RSI نزولی")
    elif rv>=70:reasons.append("RSI اشباع خرید؛ احتیاط")
    elif rv<=30:reasons.append("RSI اشباع فروش؛ احتیاط")
    if hist>0:score+=2;bull+=1;reasons.append("MACD مثبت")
    elif hist<0:score-=2;bear+=1;reasons.append("MACD منفی")
    if vr>=1.2 and score!=0:score+=1 if score>0 else -1;reasons.append("حجم بالاتر از میانگین")
    if roc>0.3:reasons.append("مومنتوم مثبت")
    elif roc<-0.3:reasons.append("مومنتوم منفی")
    hi,lo=safe_float(x.high20),safe_float(x.low20); pos=(close-lo)/(hi-lo) if hi>lo else .5
    return {"score":int(score),"bullish_votes":bull,"bearish_votes":bear,"price":close,"rsi":round(rv,2),"atr":safe_float(x.atr),"ema20":e20,"ema50":e50,"ema200":e200,"macd":safe_float(x.macd),"hist":hist,"volume_ratio":round(vr,2),"roc10_pct":round(roc,3),"range_position":round(pos,3),"reasons":reasons}
def _direction(score,threshold=2):return 1 if score>=threshold else -1 if score<=-threshold else 0
def higher_timeframe_context(analyses):
    macro=[analyses.get(x,{}).get("score",0) for x in ("1d",) if not analyses.get(x,{}).get("error")]
    structure=[analyses.get(x,{}).get("score",0) for x in ("1h","4h") if not analyses.get(x,{}).get("error")]
    macro_dir=_direction(sum(macro)/len(macro),2) if macro else 0; structure_dir=_direction(sum(structure)/len(structure),2) if structure else 0
    if macro_dir and structure_dir and macro_dir==structure_dir:bias=macro_dir
    elif macro_dir and not structure_dir:bias=macro_dir
    elif structure_dir and not macro_dir:bias=structure_dir
    else:bias=0
    return {"macro_direction":macro_dir,"structure_direction":structure_dir,"bias":bias,"macro_score":round(sum(macro)/len(macro),3) if macro else 0,"structure_score":round(sum(structure)/len(structure),3) if structure else 0}
def targets(price,atr_value,decision):
    risk=max(1.5*atr_value,price*.003)
    if decision=="LONG":stop=price-risk;vals=[price+1.2*risk,price+2*risk,price+3*risk]
    elif decision=="SHORT":stop=price+risk;vals=[price-1.2*risk,price-2*risk,price-3*risk]
    else:return {"entry":None,"stop":None,"tp1":None,"tp2":None,"tp3":None,"risk_reward_tp1":0,"risk_reward_tp2":0,"risk_reward_tp3":0}
    return {"entry":round(price,8),"stop":round(stop,8),"tp1":round(vals[0],8),"tp2":round(vals[1],8),"tp3":round(vals[2],8),"risk_reward_tp1":1.2,"risk_reward_tp2":2.0,"risk_reward_tp3":3.0}
def build_signal(symbol,market,depth,trades,derivatives,analyses):
    valid={tf:a for tf,a in analyses.items() if isinstance(a,dict) and not a.get("error") and safe_float(a.get("atr"))>0}; price=safe_float(market.get("last"))
    if not price or len(valid)<5:return {"symbol":symbol,"price":price,"decision":"NO TRADE","confidence":0,"score":0,"entry":None,"stop":None,"tp1":None,"tp2":None,"tp3":None,"reason":"داده معتبر کافی نیست؛ حداقل ۵ تایم‌فریم لازم است","invalidation":"—","timeframes":analyses}
    context=higher_timeframe_context(valid); weighted=sum(safe_float(a.get("score"))*WEIGHTS.get(tf,1) for tf,a in valid.items())/sum(WEIGHTS.get(tf,1) for tf in valid); imb=safe_float(depth.get("imbalance")); br=safe_float(trades.get("buy_ratio"),.5)
    if imb>.15:weighted+=.35
    elif imb<-.15:weighted-=.35
    if br>.58:weighted+=.35
    elif br<.42:weighted-=.35
    fr=derivatives.get("funding_rate")
    if fr is not None:
        if fr>.0005:weighted-=.15
        elif fr<-.0005:weighted+=.15
    trigger_scores=[valid.get(x,{}).get("score",0) for x in ("5m","10m") if x in valid]; setup_scores=[valid.get(x,{}).get("score",0) for x in ("15m","30m") if x in valid]; trigger_avg=sum(trigger_scores)/len(trigger_scores) if trigger_scores else 0; setup_avg=sum(setup_scores)/len(setup_scores) if setup_scores else 0
    decision="LONG" if weighted>=2.6 else "SHORT" if weighted<=-2.6 else "NO TRADE"
    if context["bias"] and decision!="NO TRADE" and _direction(weighted,2)!=context["bias"]:decision="NO TRADE"
    if context["macro_direction"] and context["structure_direction"] and context["macro_direction"]!=context["structure_direction"]:decision="NO TRADE"
    if decision=="LONG" and (trigger_avg<-1 or setup_avg<-1):decision="NO TRADE"
    if decision=="SHORT" and (trigger_avg>1 or setup_avg>1):decision="NO TRADE"
    if safe_float(depth.get("spread_pct"),999)>MAX_SPREAD_PCT:decision="NO TRADE"
    alignment_parts=[_direction(valid[name]["score"],2) for name in ("1d","4h","1h","30m","15m","10m","5m") if name in valid]; aligned=sum(1 for x in alignment_parts if x!=0 and x==(1 if decision=="LONG" else -1 if decision=="SHORT" else 0)); confidence=0 if decision=="NO TRADE" else min(95,int((abs(weighted)/5)*65+aligned/max(len(alignment_parts),1)*35)); target_source=valid.get("10m") or valid.get("15m") or valid.get("30m"); t=targets(price,safe_float(target_source.get("atr")) or price*.005,decision); reasons=[f"{tf}: {r}" for tf,a in valid.items() for r in a.get("reasons",[])]
    if context["bias"]==1:reasons.append("سوگیری تایم‌فریم‌های بالاتر: صعودی")
    elif context["bias"]==-1:reasons.append("سوگیری تایم‌فریم‌های بالاتر: نزولی")
    reason="؛ ".join(reasons[:20]) if decision!="NO TRADE" else "شرایط چندتایم‌فریمی برای سیگنال معتبر هم‌جهت نیست؛ ربات عمداً از ورود ضعیف عبور کرد"
    return {"symbol":symbol,"decision":decision,"confidence":confidence,"score":round(weighted,3),"price":price,**t,"reason":reason,"invalidation":"رسیدن قیمت به Stop Loss یا بی‌اعتبار شدن ساختار تأییدکننده" if decision!="NO TRADE" else "—","hierarchy":context,"market":market,"orderbook":depth,"recent_trades":trades,"derivatives":derivatives,"timeframes":analyses,"generated_at":now_utc(),"paper_only":True}
def get_signal_snapshot(symbol=DEFAULT_SYMBOL):
    try:
        m=market_snapshot(symbol)
        if m.get("error"):r={"symbol":symbol,"decision":"NO TRADE","confidence":0,"price":0,"reason":m["error"]};save_event("no_trade",r);return r
        d,tr,der=orderbook_snapshot(symbol),recent_trades(symbol),derivatives_snapshot(symbol); analyses={}
        for tf,cfg in TIMEFRAMES.items():
            try:analyses[tf]=timeframe_analysis(get_candles(symbol,cfg["resolution"],300))
            except Exception as e:analyses[tf]={"error":str(e),"score":0,"reasons":[]}
        r=build_signal(symbol,m,d,tr,der,analyses);save_event("signal_generated",r);return r
    except Exception as e:r={"symbol":symbol,"decision":"NO TRADE","confidence":0,"price":0,"reason":f"خطای موتور: {e}"};save_event("engine_error",r);return r

def paper_records():
    if not PAPER_JOURNAL.exists():return []
    rows=[]
    with PAPER_JOURNAL.open("r",encoding="utf-8") as f:
        for line in f:
            try:rows.append(json.loads(line))
            except json.JSONDecodeError:pass
    return rows
def daily_risk_halted():
    today=datetime.now(timezone.utc).date().isoformat(); pnl=sum(safe_float(x.get("pnl")) for x in paper_records() if x.get("status")=="CLOSED" and str(x.get("closed_at","")).startswith(today)); return pnl<=-(PAPER_START_BALANCE*DAILY_LOSS_LIMIT_PCT/100)
def paper_open(signal,quantity=1.0):
    if signal.get("decision") not in {"LONG","SHORT"}:return {"ok":False,"reason":"سیگنال قابل ثبت در Paper نیست"}
    if daily_risk_halted():return {"ok":False,"reason":"Kill Switch روزانه فعال است"}
    t={"id":f"paper-{int(time.time()*1000)}","symbol":signal["symbol"],"side":signal["decision"],"entry":signal.get("entry"),"stop":signal.get("stop"),"tp1":signal.get("tp1"),"tp2":signal.get("tp2"),"tp3":signal.get("tp3"),"quantity":quantity,"opened_at":now_utc(),"status":"OPEN"}
    with PAPER_JOURNAL.open("a",encoding="utf-8") as f:f.write(json.dumps(t,ensure_ascii=False)+"\n")
    save_event("paper_open",t);return {"ok":True,"trade":t}
def paper_close(trade,exit_price,reason="manual"):
    e,x,q=safe_float(trade.get("entry")),safe_float(exit_price),safe_float(trade.get("quantity"),1);pnl=(x-e)*q if trade.get("side")=="LONG" else (e-x)*q;c=dict(trade,exit=x,pnl=pnl,reason=reason,closed_at=now_utc(),status="CLOSED")
    with PAPER_JOURNAL.open("a",encoding="utf-8") as f:f.write(json.dumps(c,ensure_ascii=False)+"\n")
    save_event("paper_close",c);return c
def paper_stats():
    p=[safe_float(x.get("pnl")) for x in paper_records() if x.get("status")=="CLOSED"];w=[x for x in p if x>0];l=[x for x in p if x<0];gl=abs(sum(l));return {"closed":len(p),"wins":len(w),"losses":len(l),"win_rate":round(len(w)/len(p)*100,2) if p else 0,"profit_factor":round(sum(w)/gl,3) if gl else (999 if w else 0),"pnl":round(sum(p),8)}
def paper_status():return {"mode":"PAPER","balance_start":PAPER_START_BALANCE,"open_trades":sum(1 for x in paper_records() if x.get("status")=="OPEN"),"daily_loss_limit_pct":DAILY_LOSS_LIMIT_PCT,"kill_switch":daily_risk_halted(),**paper_stats()}
