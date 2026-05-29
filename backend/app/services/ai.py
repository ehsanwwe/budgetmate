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

INCOME_RANGE_MAP = {
    "lt10": 7_000_000,
    "10to20": 15_000_000,
    "20to40": 30_000_000,
    "40to80": 60_000_000,
    "gt80": 100_000_000,
}

BASE_PERSONA = (
    "تو دستیار مالی شخصی BudgetMate هستی. "
    "همیشه فارسی پاسخ بده. پاسخ‌هایت کوتاه، دقیق و کاربردی باشند. "
    "هرگز عدد نساخ — فقط بر اساس داده‌های واقعی موجود پاسخ بده."
)

TONE_DIRECTIVES = {
    "normal": "لحن دوستانه، صمیمی، کاربردی و کوتاه.",
    "roast": (
        "لحن کمی طعنه‌آمیز و طنز. وقتی کاربر بد خرج کرده، با شوخی نه با توهین بهش تذکر بده. "
        "مثال‌ها: «باز رفتی کافه؟ کیفت داره ناله می‌کنه.» / «۵ بار این هفته تاکسی! می‌دونی پیاده‌روی هم وجود داره؟». "
        "هرگز توهین نکن، فقط طنز سبک."
    ),
    "hype": (
        "لحن پرانرژی و تشویقی. از هر پیشرفت کوچک تجلیل کن. emoji و کلمات هیجانی استفاده کن. "
        "مثال‌ها: «وای چقدر عالی! 🎉 این هفته ۲۰٪ کمتر خرج کردی، آفرین!» / «داری مثل قهرمان‌ها پیش می‌ری 💪»"
    ),
}

BEHAVIOR_RULES = """قوانین گفتگو:

۱. عدد بدون واحد رو هرگز حدس نزن. اگه کاربر «۱۰»، «بیست»، «نیم» گفت، اول بپرس منظورش چیه. هرگز فرض نکن «۱۰» یعنی «۱۰ میلیون».

۲. درصد رو همیشه با درآمد واقعی کاربر حساب کن. اگه درآمد رو نداری، اول از کاربر بپرس.

۳. وقتی داده نیست (هدف، بودجه، تراکنش)، گفت‌وگو کن نه قطع. مثال بزن، سوال کامل بپرس، کاربر رو راهنمایی کن تا داده رو بسازه.

۴. اعداد بزرگ با جداکننده هزارگان و واحد «تومان»: «۱۲٬۰۰۰٬۰۰۰ تومان»."""

ACTION_SPEC = """وقتی اطلاعات کافی برای ساخت چیزی داری، آخر پیامت یه بلاک JSON اضافه کن:

برای هدف:
```json
{"action":"create_goal","title":"...","target_amount":<integer toman>,"deadline":"<jalali YYYY-MM-DD or null>"}
```

برای تراکنش:
```json
{"action":"create_transaction","amount":<integer toman>,"type":"expense|income","category":"<name>","description":"...","date":"today"}
```

برای بودجه:
```json
{"action":"set_budget","amount":<integer toman>}
```

این بلاک باید تو ```json ... ``` بسته باشه. سیستم خودش اجراش می‌کنه. تو متن visible به action اشاره نکن."""


def map_income_range(income_range: Optional[str]) -> Optional[int]:
    return INCOME_RANGE_MAP.get(income_range or "")


def build_system_prompt(context: Optional[dict] = None, chat_mode: str = "normal") -> str:
    tone = TONE_DIRECTIVES.get(chat_mode, TONE_DIRECTIVES["normal"])

    if not context:
        return "\n\n".join([BASE_PERSONA, tone, BEHAVIOR_RULES, ACTION_SPEC])

    budget = context.get("budget", {})
    spent = context.get("total_spent_this_month", 0)
    income_tx = context.get("total_income_this_month", 0)
    remaining = context.get("remaining_budget", 0)
    budget_amount = budget.get("amount") if isinstance(budget, dict) else budget

    user_ctx_parts = ["\nاطلاعات مالی واقعی کاربر:"]
    user_ctx_parts.append(f"- تاریخ امروز: {context.get('current_gregorian_date')}")
    user_ctx_parts.append(f"- ماه/سال جلالی: {context.get('current_jalali_month')}/{context.get('current_jalali_year')}")
    user_ctx_parts.append(f"- بودجه ماه جاری: {int(budget_amount or 0):,} تومان")
    user_ctx_parts.append(f"- هزینه این ماه: {int(spent or 0):,} تومان")
    user_ctx_parts.append(f"- درآمد ثبت‌شده این ماه: {int(income_tx or 0):,} تومان")
    user_ctx_parts.append(f"- مانده بودجه: {int(remaining or 0):,} تومان")
    user_ctx_parts.append(f"- درصد مصرف بودجه: {context.get('budget_used_percent', 0)}٪")

    income_range = context.get("user", {}).get("income_range")
    estimated_income = map_income_range(income_range)
    if estimated_income:
        user_ctx_parts.append(f"- درآمد ماهانه تخمینی کاربر: {estimated_income:,} تومان (بر اساس بازه {income_range})")
    else:
        user_ctx_parts.append("- درآمد ماهانه: اعلام نشده (اگه نیاز به درصد داری، از کاربر بپرس)")

    if context.get("top_expense_categories"):
        user_ctx_parts.append("- دسته‌های پرهزینه:")
        for cat in context["top_expense_categories"]:
            user_ctx_parts.append(f"  * {cat['name']}: {cat['amount']:,} تومان")

    if context.get("active_goals"):
        user_ctx_parts.append("- اهداف فعال:")
        for goal in context["active_goals"]:
            user_ctx_parts.append(
                f"  * {goal['title']}: مانده {goal['remaining_amount']:,} از {goal['target_amount']:,} تومان"
            )

    if context.get("recent_transactions"):
        user_ctx_parts.append("- آخرین تراکنش‌ها:")
        for tx in context["recent_transactions"][:5]:
            user_ctx_parts.append(
                f"  * {tx['date']} - {tx['type']} - {tx['amount']:,} - {tx.get('description') or ''}"
            )

    user_context_block = "\n".join(user_ctx_parts)
    return "\n\n".join([BASE_PERSONA, tone, user_context_block, BEHAVIOR_RULES, ACTION_SPEC])


# Keep old name as alias for callers that pass context only (finance_agent._llm_classify)
def _build_system_prompt(context: Optional[dict] = None) -> str:
    return build_system_prompt(context, chat_mode="normal")


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
    url = "http://188.136.214.220:11434/v1/chat/completions"
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


async def get_ai_reply(
    user_message: str,
    context: Optional[dict] = None,
    chat_mode: str = "normal",
) -> str:
    messages = [
        {"role": "system", "content": build_system_prompt(context, chat_mode)},
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


async def stream_ai_reply(
    user_message: str,
    context: Optional[dict] = None,
    chat_mode: str = "normal",
) -> AsyncIterator[str]:
    reply = await get_ai_reply(user_message, context, chat_mode)
    for i, word in enumerate(reply.split(" ")):
        yield word if i == 0 else " " + word
        await asyncio.sleep(0.05)
