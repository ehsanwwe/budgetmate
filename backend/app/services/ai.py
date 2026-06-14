from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional, Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "در حال حاضر دستیار هوشمند در دسترس نیست. لطفا بعدا تلاش کنید."


class LLMProviderError(RuntimeError):
    pass


class LLMProviderConfigError(LLMProviderError):
    pass


class OpenAIProviderError(LLMProviderError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str

    async def complete_text(self, messages: list[dict]) -> str:
        ...

    async def complete_json(self, messages: list[dict]) -> str:
        ...


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str):
        api_key = (api_key or "").strip()
        model = (model or "").strip()
        if not api_key:
            raise LLMProviderConfigError("OPENAI_API_KEY is required when AI_PROVIDER=openai")
        if not model:
            raise LLMProviderConfigError("OPENAI_MODEL is required when AI_PROVIDER=openai")
        self.api_key = api_key
        self.model = model

    async def complete_text(self, messages: list[dict]) -> str:
        return await self._complete(messages, require_json=False)

    async def complete_json(self, messages: list[dict]) -> str:
        return await self._complete(messages, require_json=True)

    async def _complete(self, messages: list[dict], require_json: bool) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict = {"model": self.model, "messages": messages, "stream": False}
        if require_json:
            body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", json=body, headers=headers)
            if response.status_code != 200:
                raise OpenAIProviderError(f"OpenAI returned HTTP {response.status_code}")
            return response.json()["choices"][0]["message"]["content"]


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = (base_url or "http://localhost:11434").strip().rstrip("/")
        self.model = (model or "gpt-oss:20b").strip()
        if not self.model:
            raise LLMProviderConfigError("OLLAMA_MODEL is required when AI_PROVIDER=ollama")

    async def complete_text(self, messages: list[dict]) -> str:
        return await self._complete(messages, require_json=False)

    async def complete_json(self, messages: list[dict]) -> str:
        return await self._complete(messages, require_json=True)

    async def _complete(self, messages: list[dict], require_json: bool) -> str:
        body: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if require_json:
            body["format"] = "json"

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=body)
            if response.status_code != 200:
                raise LLMProviderError(f"Ollama returned HTTP {response.status_code}")
            payload = response.json()
            message = payload.get("message") or {}
            content = message.get("content")
            if content is None:
                content = payload.get("response")
            if not isinstance(content, str):
                raise LLMProviderError("Ollama response did not include text content")
            return content


def _selected_provider_name() -> str:
    explicit = (settings.AI_PROVIDER or "").strip().lower()
    if explicit:
        if explicit not in {"openai", "ollama"}:
            raise LLMProviderConfigError("AI_PROVIDER must be either 'openai' or 'ollama'")
        return explicit
    if (settings.OPENAI_API_KEY or "").strip():
        return "openai"
    return "ollama"


def get_llm_provider() -> LLMProvider:
    provider_name = _selected_provider_name()
    if provider_name == "openai":
        return OpenAIProvider(settings.OPENAI_API_KEY, settings.OPENAI_MODEL)
    return OllamaProvider(settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)


def resolve_ai_provider(model: str | None = None) -> tuple[str, str]:
    provider = get_llm_provider()
    if model and provider.name == "openai":
        provider = OpenAIProvider(settings.OPENAI_API_KEY, model)
    return provider.name, provider.model


def log_ai_provider_config() -> None:
    try:
        provider = get_llm_provider()
        logger.info("AI provider configured: provider=%s model=%s", provider.name, provider.model)
    except LLMProviderError as exc:
        logger.warning("AI provider is not configured: %s", exc)


async def get_ai_chat_completion(messages: list[dict], require_json: bool = False) -> str:
    provider = get_llm_provider()
    if require_json:
        return await provider.complete_json(messages)
    return await provider.complete_text(messages)


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
    except LLMProviderError as exc:
        logger.warning("AI chat unavailable: %s", exc)
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
