import os, json, time, requests
from pathlib import Path
from datetime import datetime, timezone

DATA=Path("data")
DATA.mkdir(exist_ok=True)
JOURNAL=DATA/"journal.jsonl"

def save_event(event, payload):
    with JOURNAL.open("a",encoding="utf-8") as f:
        f.write(json.dumps({
            "ts":datetime.now(timezone.utc).isoformat(),
            "event":event,"payload":payload
        },ensure_ascii=False)+"\n")

def wallex_snapshot(symbol="BTCUSDT"):
    """Public market snapshot scaffold. Verify endpoints before production."""
    url="https://api.wallex.ir/v1/markets"
    try:
        r=requests.get(url,timeout=10)
        r.raise_for_status()
        data=r.json()
        item=data.get("result",{}).get("symbols",{}).get(symbol,{})
        stats=item.get("stats",{})
        return {
            "symbol":symbol,
            "bid":float(stats.get("bidPrice",0) or 0),
            "ask":float(stats.get("askPrice",0) or 0),
            "volume24h":float(stats.get("24h_volume",0) or 0)
        }
    except Exception as e:
        return {"symbol":symbol,"error":str(e)}

def get_signal_snapshot():
    w=wallex_snapshot(os.getenv("SYMBOL","BTCUSDT"))
    price=(w.get("bid",0)+w.get("ask",0))/2 if w.get("bid") and w.get("ask") else 0
    # Conservative placeholder: no live signal until richer feeds + backtests are connected.
    return {
        "symbol":w["symbol"], "price":price, "decision":"NO TRADE",
        "confidence":0,
        "entry":None,"stop":None,"tp1":None,"tp2":None,
        "reason":"داده کافی برای صدور سیگنال معتبر در نسخه اولیه وجود ندارد.",
        "invalidation":"—",
        "wallex":w
    }

def review_with_ai(client, snapshot):
    prompt=f"""
تو ناظر یک سیستم تحلیل کریپتو هستی. این گزارش خام را بررسی کن:
{json.dumps(snapshot,ensure_ascii=False)}

وظیفه:
1) تناقض‌ها و داده‌های کم را مشخص کن.
2) بگو چه داده‌هایی برای تصمیم کوتاه‌مدت BTC لازم است.
3) اگر سیگنال صادر نشده، دلیل درست بودن NO TRADE را بررسی کن.
4) پیشنهادهای فنی برای ارتقای موتور بده.
5) هرگز ادعای سود تضمینی یا قطعیت نکن.
6) فقط پیشنهاد بده؛ کد/نسخه واقعی را خودکار تغییر نده.
"""
    resp=client.responses.create(
        model=os.getenv("OPENAI_MODEL","gpt-5.6"),
        tools=[{"type":"web_search"}],
        input=prompt
    )
    return resp.output_text
