import json
import os
from openai import OpenAIError


def review_with_ai(client, snapshot):
    """Advisory-only second-pass review of an existing market snapshot.

    Never places orders, changes trading mode, or overrides the deterministic engine.
    """
    if client is None:
        return "⚠️ OPENAI_API_KEY تنظیم نشده است."

    payload = {
        "symbol": snapshot.get("symbol"),
        "decision": snapshot.get("decision"),
        "confidence": snapshot.get("confidence"),
        "score": snapshot.get("score"),
        "entry": snapshot.get("entry"),
        "stop": snapshot.get("stop"),
        "tp1": snapshot.get("tp1"),
        "tp2": snapshot.get("tp2"),
        "tp3": snapshot.get("tp3"),
        "reason": snapshot.get("reason"),
        "invalidation": snapshot.get("invalidation"),
        "hierarchy": snapshot.get("hierarchy"),
        "timeframes": snapshot.get("timeframes"),
        "derivatives": snapshot.get("derivatives"),
        "market": snapshot.get("market"),
        "orderbook": snapshot.get("orderbook"),
    }

    model = os.getenv("OPENAI_MODEL", "gpt-5.6").strip() or "gpt-5.6"
    system = (
        "You are a critical second-pass reviewer for a crypto market-analysis bot. "
        "Review only the supplied snapshot; do not invent missing data. "
        "Separate observations from interpretations. Check multi-timeframe agreement, "
        "market regime, momentum, volatility, liquidity/order-book evidence, derivatives, "
        "entry/stop placement, reward-to-risk, and invalidation. Explicitly identify "
        "contradictions and stale/missing inputs. If evidence is weak or conflicting, "
        "prefer NO TRADE. Confidence is not a probability of profit and must not be "
        "presented as a guarantee. This is advisory analysis only and must never place "
        "or enable a real order. Respond in Persian with these headings: جمع‌بندی, "
        "شواهد موافق, تناقض‌ها/ریسک‌ها, کیفیت TP/SL, نتیجه نهایی. Keep it concise."
    )
    try:
        response = client.with_options(timeout=20.0, max_retries=1).responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            max_output_tokens=900,
        )
        text = getattr(response, "output_text", "")
        return text.strip() if text else "⚠️ پاسخ متنی از سرویس AI دریافت نشد."
    except OpenAIError as e:
        return f"⚠️ خطای سرویس OpenAI: {e}"
    except Exception as e:
        return f"⚠️ خطای AI: {e}"
