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


def _strip_provider(model: str) -> str:
    return model.split("/", 1)[-1] if "/" in model else model


def _openai_model_candidates() -> list[str]:
    candidates: list[str] = []
    if settings.OPENAI_MODEL:
        candidates.append(settings.OPENAI_MODEL)
    for model in [settings.PRIMARY_MODEL] + settings.fallback_models_list:
        if model.startswith("openai/"):
            candidates.append(_strip_provider(model))
    return [model for index, model in enumerate(candidates) if model and model not in candidates[:index]]


def resolve_ai_provider(model: str | None = None) -> tuple[str, str]:
    explicit = (settings.AI_PROVIDER or "").strip().lower()
    if explicit == "openai":
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("AI_PROVIDER=openai requires OPENAI_API_KEY")
        candidates = _openai_model_candidates()
        if not candidates:
            raise RuntimeError("OpenAI provider requires OPENAI_MODEL or an openai/* model")
        return "openai", candidates[0]
    if explicit in {"openclaw", "ollama"}:
        return explicit, _strip_provider(model or settings.PRIMARY_MODEL)
    if explicit:
        logger.warning("Unknown AI_PROVIDER=%s; using automatic provider resolution", explicit)

    if settings.OPENAI_API_KEY:
        candidates = _openai_model_candidates()
        if candidates:
            return "openai", candidates[0]
        raise RuntimeError("OPENAI_API_KEY is configured but no OpenAI model is configured")

    selected = model or settings.PRIMARY_MODEL
    if selected.startswith("ollama/"):
        return "ollama", _strip_provider(selected)
    if selected.startswith("openai/"):
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OpenAI model selected but OPENAI_API_KEY is not configured")
        return "openai", _strip_provider(selected)
    return "openclaw", selected


def log_ai_provider_config() -> None:
    try:
        provider, model = resolve_ai_provider(settings.PRIMARY_MODEL)
        logger.info("AI provider configured: provider=%s model=%s", provider, model)
    except Exception as exc:
        logger.warning("AI provider configuration issue: %s", exc)

INCOME_RANGE_LABELS = {
    "lt10": "کمتر از ۱۰ میلیون تومان",
    "10to20": "بین ۱۰ تا ۲۰ میلیون تومان",
    "20to40": "بین ۲۰ تا ۴۰ میلیون تومان",
    "40to80": "بین ۴۰ تا ۸۰ میلیون تومان",
    "gt80": "بیشتر از ۸۰ میلیون تومان",
    "prefer_not": "ثبت نشده",
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

۲. درصد رو این‌طور حساب کن:
   - اگه درآمد دقیق (monthly_income) ثبت شده، همون عدد رو به کار ببر.
   - اگه فقط بازه درآمد ثبت شده (مثل «بین ۴۰ تا ۸۰ میلیون»)، **فوری یه بازه بده** مثل «۲۰٪ یعنی بین ۸ تا ۱۶ میلیون ماهانه» و بعد عدد دقیق بخواه.
   - هرگز یه عدد تخمینی تکی رو به عنوان واقعیت ذکر نکن. اگه بازه داری، بازه بده.

۳. وقتی داده نیست (هدف، بودجه، تراکنش)، گفت‌وگو کن نه قطع. مثال بزن، سوال کامل بپرس، کاربر رو راهنمایی کن تا داده رو بسازه.

۴. اعداد بزرگ با جداکننده هزارگان و واحد «تومان»: «۱۲٬۰۰۰٬۰۰۰ تومان».

۵. اگه کاربر بازه درآمد «بیشتر از ۸۰ میلیون» انتخاب کرده، عدد واقعی‌اش می‌تونه صدها میلیون یا حتی میلیاردها تومان باشه. هیچ‌وقت برای این بازه عدد مشخصی فرض نکن — بازه رو تأیید کن و عدد دقیق بخواه."""

CONVERSATION_RULES = """رفتار در گفتگو:

۱. **به تاریخچه گفتگو دقیق توجه کن.** اگه قبلاً از کاربر سوالی پرسیدی و کاربر جواب داده، **هرگز** دوباره نپرس. مثال:
   - تو: «درآمد ماهانه‌ات چقدره؟»
   - کاربر: «۴۸ میلیون»
   - تو: «پس ۲۰٪ از ۴۸ میلیون میشه ۹٬۶۰۰٬۰۰۰ تومان…» (محاسبه و ادامه)
   نه: «منظورت کدوم عدد است؟» (این اشتباه است!)

۲. **اگه بازه درآمد در اطلاعات کاربر هست، از همون اول استفاده کن.** مثال:
   - کاربر: «۲۰٪ سیو کنم»
   - بازه درآمد کاربر: ۴۰ تا ۸۰ میلیون
   - تو: «۲۰٪ پس‌انداز عالیه! بر اساس بازه درآمدت، یعنی بین ۸ تا ۱۶ میلیون ماهانه. اگه عدد دقیق درآمدت رو بهم بگی، دقیق‌تر حساب می‌کنم.»

۳. **وقتی کاربر یه عدد دقیق گفت، اون رو به عنوان جواب سوال قبلی بپذیر، نه چیز جدید.** اگه شک داری برای چیه، **به سوال قبلی خودت برگرد**. هرگز کاربر رو با سوال‌های متعدد گیج نکن.

۴. **پیشنهاد ذخیره دائمی فقط بعد از دادن جواب اصلی.** اگه کاربر گفت «۴۸ میلیون درآمد دارم»، اول محاسبه رو بده، بعد می‌تونی بپرسی «می‌خوای این رو به‌عنوان درآمد دقیقت ثبت کنم؟» و action set_income رو بزنی."""

ACTION_RULES = """قوانین مهم برای ساخت action (JSON block):

۱. **فقط وقتی action بساز که کاربر واضح بگه چیزی رخ داده یا می‌خواد ثبت کنه.** مثال‌های درست:
   - «امروز ۲۰۰ هزار تومان نون خریدم» → بله، create_transaction
   - «حقوقم ۵۰ میلیون گرفتم» → بله، create_transaction (income)
   - «هدف من خرید لپ‌تاپ ۸۰ میلیونیه» → بله، create_goal
   - «بودجه این ماه ۲۰ میلیون باشه» → بله، set_budget

   مثال‌های غلط که نباید action بسازی:
   - «چطور ۲۰ درصد سیو کنم» → فقط مشاوره بده. هیچ action نساز.
   - «چقدر ماهانه پس‌انداز کنم؟» → فقط راهنمایی. هیچ action نساز.
   - «۱۰ روز دیگه چه کار کنم؟» → عدد ربطی به پول نداره. هیچ action نساز.
   - «اگه ۵ میلیون داشته باشم» → فرضیه است نه واقعیت. هیچ action نساز.

۲. **اگه عدد، درصد یا واحد زمان است (نه مبلغ پولی)، action نساز.**
   - «۲۰ درصد» → نه
   - «۵ سال» → نه
   - «۳ ماه» → نه
   - «۲۰ تومان» یا «۲۰ هزار تومان» → اگه context واضحه بله

۳. **مبلغ کمتر از ۱۰۰۰ تومان معقول نیست.** اگه عددی که استخراج می‌کنی کمتر از ۱۰۰۰ شد، یعنی احتمالاً واحد رو اشتباه فهمیدی. هرگز transaction با مبلغ < 1000 نساز.

۴. **اگه شک داری، نساز.** بهتر است بپرسی «منظورت اینه که ۲۰۰ هزار تومان نون خریدی؟ ثبت کنم؟» تا اینکه یک تراکنش غلط بسازی.

۵. **توضیح تراکنش باید کامل و خوانا باشه.** هرگز جمله رو نصفه نکن. اگه توضیح کاربر خیلی بلنده، خلاصه‌اش کن (مثل «خرید نون» به جای «امروز رفتم نون خریدم»).

۶. **برای راهنمایی و مشاوره، فقط متن جواب بده — هیچ JSON اضافه نکن.** action block فقط برای ثبت داده‌های واقعی است."""

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

برای ثبت درآمد دقیق ماهانه (وقتی کاربر عدد دقیق درآمد ماهانه‌اش رو اعلام کرد):
```json
{"action":"set_income","amount":<integer toman>}
```

این بلاک باید تو ```json ... ``` بسته باشه. سیستم خودش اجراش می‌کنه. تو متن visible به action اشاره نکن.

---
نمونه‌های راهنما:

نمونه ۱:
کاربر: «میخام ۲۰ درصد سیو کنم» (بازه درآمد ثبت‌شده: ۴۰ تا ۸۰ میلیون)
جواب درست (بدون JSON — از بازه استفاده کن):
«۲۰٪ پس‌انداز عالیه! بر اساس بازه درآمدت، این مبلغ بین ۸ تا ۱۶ میلیون ماهانه میشه. اگه عدد دقیق درآمدت رو بهم بگی، دقیق‌تر حساب می‌کنم.»

نمونه ۲:
کاربر: «امروز ۲۰۰ هزار تومان نون خریدم»
جواب درست (با JSON):
«باشه، ثبتش می‌کنم.»

```json
{"action":"create_transaction","amount":200000,"type":"expense","category":"غذا و خوراک","description":"خرید نون","date":"today"}
```

نمونه ۳:
کاربر: «اگه ماهی ۵ میلیون پس‌انداز کنم چی میشه؟»
جواب درست (بدون JSON — فرضیه است):
«اگه ماهانه ۵ میلیون پس‌انداز کنی، تو یک سال ۶۰ میلیون جمع می‌کنی. می‌خوای این هدف رو ثبت کنم؟»

نمونه ۴:
کاربر: «بودجه این ماهم رو ۱۵ میلیون بذار»
جواب درست (با JSON):
«حتماً، بودجه این ماه رو روی ۱۵ میلیون تنظیم می‌کنم.»

```json
{"action":"set_budget","amount":15000000}
```"""


def income_range_label(income_range: Optional[str]) -> str:
    return INCOME_RANGE_LABELS.get(income_range or "", "ثبت نشده")


_INCOME_RANGE_HINTS = {
    "lt10": "برای ۲۰٪ مثال: کمتر از ۲ میلیون ماهانه.",
    "10to20": "برای ۲۰٪ مثال: بین ۲ تا ۴ میلیون ماهانه.",
    "20to40": "برای ۲۰٪ مثال: بین ۴ تا ۸ میلیون ماهانه.",
    "40to80": "برای ۲۰٪ مثال: بین ۸ تا ۱۶ میلیون ماهانه.",
    "gt80": "برای ۲۰٪ مثال: بیش از ۱۶ میلیون ماهانه.",
}


def _income_range_hint(income_range: Optional[str]) -> str:
    return _INCOME_RANGE_HINTS.get(income_range or "", "")


def build_system_prompt(context: Optional[dict] = None, chat_mode: str = "normal") -> str:
    tone = TONE_DIRECTIVES.get(chat_mode, TONE_DIRECTIVES["normal"])

    if not context:
        return "\n\n".join([BASE_PERSONA, tone, BEHAVIOR_RULES, CONVERSATION_RULES, ACTION_RULES, ACTION_SPEC])

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

    user_info = context.get("user", {})
    income_range = user_info.get("income_range")
    monthly_income = user_info.get("monthly_income")
    if monthly_income and monthly_income > 0:
        user_ctx_parts.append(f"- درآمد دقیق ماهانه کاربر: {int(monthly_income):,} تومان (ثبت‌شده — برای محاسبه‌های درصد از همین عدد استفاده کن).")
    elif income_range and income_range not in ("prefer_not",):
        label = income_range_label(income_range)
        range_hint = _income_range_hint(income_range)
        user_ctx_parts.append(
            f"- بازه درآمد ماهانه کاربر: {label}. {range_hint} "
            f"عدد دقیق ثبت نشده — برای محاسبه‌های درصد از بازه استفاده کن و بعد عدد دقیق بخواه."
        )
    else:
        user_ctx_parts.append("- درآمد ماهانه: اعلام نشده — از کاربر بخواه عدد دقیق بگه.")

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
    return "\n\n".join([BASE_PERSONA, tone, user_context_block, BEHAVIOR_RULES, CONVERSATION_RULES, ACTION_RULES, ACTION_SPEC])


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


async def _try_openai(messages: list, model: str) -> Optional[str]:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI")
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {"model": model, "messages": messages, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", json=body, headers=headers)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            logger.warning("OpenAI returned %s: %s", resp.status_code, resp.text[:500])
    except Exception as exc:
        logger.warning("OpenAI error: %s", exc)
    return None


async def get_ai_reply(
    user_message: str,
    context: Optional[dict] = None,
    chat_mode: str = "normal",
    history: Optional[list[dict]] = None,
) -> str:
    messages = (
        [{"role": "system", "content": build_system_prompt(context, chat_mode)}]
        + (history or [])
        + [{"role": "user", "content": user_message}]
    )
    logger.debug("AI messages count: %d (history=%d)", len(messages), len(history or []))

    for model in [settings.PRIMARY_MODEL] + settings.fallback_models_list:
        try:
            provider, provider_model = resolve_ai_provider(model)

            reply = None
            if provider == "openclaw":
                reply = await _try_openclaw(messages, model)
            elif provider == "ollama":
                reply = await _try_ollama(messages, provider_model)
            elif provider == "openai":
                reply = await _try_openai(messages, provider_model)

            if reply:
                return reply
        except Exception as exc:
            logger.error("Model %s failed: %s", model, exc)

    return FALLBACK_MESSAGE


async def get_ai_chat_completion(messages: list[dict], require_json: bool = False) -> str:
    """Low-level provider call for backend-controlled prompts.

    This bypasses the legacy visible chat/action prompt so orchestrators can
    send their own strict system messages while reusing the configured provider
    and model waterfall.
    """
    for model in [settings.PRIMARY_MODEL] + settings.fallback_models_list:
        try:
            provider, provider_model = resolve_ai_provider(model)

            reply = None
            if provider == "openclaw":
                reply = await _try_openclaw(messages, model)
            elif provider == "ollama":
                reply = await _try_ollama(messages, provider_model)
            elif provider == "openai":
                reply = await _try_openai(messages, provider_model)

            if reply:
                return reply
        except Exception as exc:
            logger.error("Model %s failed: %s", model, exc)

    return "{}" if require_json else FALLBACK_MESSAGE


async def stream_ai_reply(
    user_message: str,
    context: Optional[dict] = None,
    chat_mode: str = "normal",
    history: Optional[list[dict]] = None,
) -> AsyncIterator[str]:
    reply = await get_ai_reply(user_message, context, chat_mode, history=history)
    for i, word in enumerate(reply.split(" ")):
        yield word if i == 0 else " " + word
        await asyncio.sleep(0.05)
