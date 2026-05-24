import asyncio
import logging
from typing import AsyncIterator, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "در حال حاضر دستیار هوشمند در دسترس نیست. لطفا بعدا تلاش کنید."

OPENCLAW_PATHS = [
    "/v1/chat/completions",
    "/agents/main/chat",
    "/api/v1/chat/completions",
]


def _build_system_prompt(context: Optional[dict] = None) -> str:
    base = (
        "تو دستیار مالی شخصی BudgetMate هستی. همیشه فارسی، کوتاه، دقیق و کاربردی پاسخ بده. "
        "فقط بر اساس داده‌های واقعی موجود در زمینه مالی کاربر عدد بده و هرگز عدد نساز. "
        "مبلغ‌ها را با جداکننده هزارگان و واحد تومان نمایش بده."
    )
    if not context:
        return base

    budget = context.get("budget", {})
    spent = context.get("total_spent_this_month", context.get("spent", 0))
    income = context.get("total_income_this_month", 0)
    remaining = context.get("remaining_budget", context.get("remaining", 0))
    budget_amount = budget.get("amount") if isinstance(budget, dict) else budget

    parts = [base, "\nاطلاعات مالی واقعی کاربر:"]
    parts.append(f"- تاریخ امروز: {context.get('current_gregorian_date')}")
    parts.append(f"- ماه/سال جلالی: {context.get('current_jalali_month')}/{context.get('current_jalali_year')}")
    parts.append(f"- بودجه ماه جاری: {int(budget_amount or 0):,} تومان")
    parts.append(f"- هزینه این ماه: {int(spent or 0):,} تومان")
    parts.append(f"- درآمد این ماه: {int(income or 0):,} تومان")
    parts.append(f"- مانده بودجه: {int(remaining or 0):,} تومان")
    parts.append(f"- درصد مصرف بودجه: {context.get('budget_used_percent', 0)}٪")

    if context.get("top_expense_categories"):
        parts.append("- دسته‌های پرهزینه:")
        for cat in context["top_expense_categories"]:
            parts.append(f"  * {cat['name']}: {cat['amount']:,} تومان")

    if context.get("active_goals"):
        parts.append("- اهداف فعال:")
        for goal in context["active_goals"]:
            parts.append(f"  * {goal['title']}: مانده {goal['remaining_amount']:,} از {goal['target_amount']:,} تومان")

    if context.get("recent_transactions"):
        parts.append("- آخرین تراکنش‌ها:")
        for tx in context["recent_transactions"][:5]:
            parts.append(f"  * {tx['date']} - {tx['type']} - {tx['amount']:,} - {tx.get('description') or ''}")

    return "\n".join(parts)


async def _try_openclaw(messages: list, model: str) -> Optional[str]:
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
                if resp.status_code == 404:
                    continue
                logger.warning("OpenClaw %s returned %s: %s", path, resp.status_code, resp.text[:500])
                return None
            except Exception as exc:
                logger.warning("OpenClaw %s error: %s", path, exc)
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
            logger.warning("Ollama returned %s: %s", resp.status_code, resp.text[:500])
    except Exception as exc:
        logger.warning("Ollama error: %s", exc)
    return None


async def get_ai_reply(user_message: str, context: Optional[dict] = None) -> str:
    messages = [
        {"role": "system", "content": _build_system_prompt(context)},
        {"role": "user", "content": user_message},
    ]

    for model in [settings.PRIMARY_MODEL] + settings.fallback_models_list:
        try:
            provider = settings.AI_PROVIDER
            if "/" in model:
                prefix = model.split("/", 1)[0]
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
                reply = await _try_ollama(messages, model.split("/", 1)[-1])

            if reply:
                return reply
        except Exception as exc:
            logger.error("Model %s failed: %s", model, exc)

    return FALLBACK_MESSAGE


async def stream_ai_reply(user_message: str, context: Optional[dict] = None) -> AsyncIterator[str]:
    reply = await get_ai_reply(user_message, context)
    for i, word in enumerate(reply.split(" ")):
        yield word if i == 0 else " " + word
        await asyncio.sleep(0.05)
