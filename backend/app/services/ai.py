from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "در حال حاضر دستیار هوشمند در دسترس نیست. لطفا بعدا تلاش کنید."


class OpenAIProviderError(RuntimeError):
    pass


def resolve_ai_provider(model: str | None = None) -> tuple[str, str]:
    if not settings.OPENAI_API_KEY:
        raise OpenAIProviderError("OPENAI_API_KEY is required for the active AI provider")
    selected_model = (model or settings.OPENAI_MODEL or "").strip()
    if not selected_model:
        raise OpenAIProviderError("OPENAI_MODEL is required for the active AI provider")
    return "openai", selected_model


def log_ai_provider_config() -> None:
    try:
        provider, model = resolve_ai_provider()
        logger.info("AI provider configured: provider=%s model=%s", provider, model)
    except OpenAIProviderError as exc:
        logger.warning("AI provider is not configured: %s", exc)


async def _call_openai(messages: list[dict], model: str, require_json: bool = False) -> str:
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body: dict = {"model": model, "messages": messages, "stream": False}
    if require_json:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", json=body, headers=headers)
        if response.status_code != 200:
            raise OpenAIProviderError(f"OpenAI returned HTTP {response.status_code}")
        return response.json()["choices"][0]["message"]["content"]


async def get_ai_chat_completion(messages: list[dict], require_json: bool = False) -> str:
    """OpenAI-only provider call for backend-controlled prompts."""
    _, model = resolve_ai_provider()
    return await _call_openai(messages, model, require_json=require_json)


async def get_ai_reply(
    user_message: str,
    context: Optional[dict] = None,
    chat_mode: str = "normal",
    history: Optional[list[dict]] = None,
) -> str:
    system = (
        "You are BudgetMate, a Persian-first personal finance assistant. "
        "Answer in concise Persian. Do not output JSON, SQL, or hidden tool text."
    )
    messages = [{"role": "system", "content": system}] + (history or []) + [{"role": "user", "content": user_message}]
    try:
        return await get_ai_chat_completion(messages)
    except OpenAIProviderError as exc:
        logger.warning("OpenAI chat unavailable: %s", exc)
        return FALLBACK_MESSAGE


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
