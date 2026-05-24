import asyncio
import logging
from typing import AsyncIterator, List, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "در حال حاضر دستیار هوشمند در دسترس نیست. لطفاً بعداً تلاش کنید."

OPENCLAW_PATHS = [
    "/v1/chat/completions",
    "/agents/main/chat",
    "/api/v1/chat/completions",
]


def _build_system_prompt(context: Optional[dict] = None) -> str:
    base = (
        "تو یک دستیار مالی شخصی به نام «بادجت‌میت» هستی. "
        "همیشه به فارسی، صمیمی، کوتاه و کاربردی پاسخ بده. "
        "اعداد را با جداکننده هزارگان نمایش بده و واحد را «تومان» بگذار. "
        "هیچ‌گاه به انگلیسی پاسخ نده."
    )
    if not context:
        return base

    parts = [base, "\n\nاطلاعات مالی کاربر:"]
    if context.get("budget"):
        parts.append(f"- بودجه ماه جاری: {context['budget']:,} تومان")
    if context.get("spent") is not None:
        parts.append(f"- مجموع هزینه‌های این ماه: {context['spent']:,} تومان")
    if context.get("remaining") is not None:
        parts.append(f"- مانده بودجه: {context['remaining']:,} تومان")
    if context.get("top_categories"):
        parts.append("- ۳ دسته‌بندی پرهزینه:")
        for cat in context["top_categories"]:
            parts.append(f"  * {cat['name']}: {cat['amount']:,} تومان")
    if context.get("goals"):
        parts.append("- اهداف مالی فعال:")
        for goal in context["goals"]:
            parts.append(f"  * {goal['title']}: {goal['current']:,} از {goal['target']:,} تومان")
    return "\n".join(parts)


async def _try_openclaw(messages: list, model: str, stream: bool = False) -> Optional[str]:
    headers = {
        "Authorization": f"Bearer {settings.OPENCLAW_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {"model": model, "messages": messages, "stream": False}

    async with httpx.AsyncClient(timeout=60) as client:
        for path in OPENCLAW_PATHS:
            url = settings.OPENCLAW_URL.rstrip("/") + path
            try:
                resp = await client.post(url, json=body, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                elif resp.status_code == 404:
                    continue
                else:
                    logger.warning(f"OpenClaw {path} returned {resp.status_code}: {resp.text[:500]}")
                    return None
            except Exception as e:
                logger.warning(f"OpenClaw {path} error: {e}")
                continue
    return None


async def _try_ollama(messages: list, model: str) -> Optional[str]:
    url = "http://localhost:11434/v1/chat/completions"
    body = {"model": model, "messages": messages, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=body)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Ollama error: {e}")
    return None


async def get_ai_reply(user_message: str, context: Optional[dict] = None) -> str:
    system_prompt = _build_system_prompt(context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    all_models = [settings.PRIMARY_MODEL] + settings.fallback_models_list

    for model in all_models:
        try:
            provider = settings.AI_PROVIDER
            if "/" in model:
                prefix = model.split("/")[0]
                if prefix == "ollama":
                    provider = "ollama"
                elif prefix == "openai":
                    provider = "openai"
                else:
                    provider = "openclaw"

            reply = None
            if provider == "openclaw":
                reply = await _try_openclaw(messages, model)
            elif provider == "ollama":
                ollama_model = model.split("/", 1)[-1] if "/" in model else model
                reply = await _try_ollama(messages, ollama_model)

            if reply:
                return reply
        except Exception as e:
            logger.error(f"Model {model} failed: {e}")
            continue

    return FALLBACK_MESSAGE


async def stream_ai_reply(user_message: str, context: Optional[dict] = None) -> AsyncIterator[str]:
    reply = await get_ai_reply(user_message, context)
    # Stream word by word for SSE effect
    words = reply.split(" ")
    for i, word in enumerate(words):
        if i == 0:
            yield word
        else:
            yield " " + word
        await asyncio.sleep(0.05)
