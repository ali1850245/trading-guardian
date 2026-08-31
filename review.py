import json
import os
from openai import OpenAIError


def review_with_ai(client, snapshot):
    """Generate a concise AI review of a signal snapshot.

    Advisory only: this function never places orders or changes trading mode.
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
        "hierarchy": snapshot.get("hierarchy"),
    }

    model = os.getenv("OPENAI_MODEL", "gpt-5.6").strip() or "gpt-5.6"

    try:
        response = client.with_options(timeout=30.0, max_retries=1).responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Review the supplied crypto signal snapshot critically. "
                        "Do not claim certainty or guaranteed profit. Identify supporting "
                        "evidence, contradictions, missing data, and whether NO TRADE "
                        "would be safer. This is analysis only; do not provide order-"
                        "execution instructions. Respond in Persian, concise and structured."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        text = getattr(response, "output_text", "")
        return text.strip() if text else "⚠️ پاسخ متنی از سرویس AI دریافت نشد."
    except OpenAIError as e:
        return f"⚠️ خطای سرویس OpenAI: {e}"
    except Exception as e:
        return f"⚠️ خطای AI: {e}"
