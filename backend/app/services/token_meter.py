from __future__ import annotations

from math import ceil


def estimate_tokens(text: str | None) -> int:
    normalized = (text or "").strip()
    return max(1, ceil(len(normalized) / 3))


def estimate_chat_usage(prompt_text: str, completion_text: str) -> dict[str, int]:
    prompt_tokens = estimate_tokens(prompt_text)
    completion_tokens = estimate_tokens(completion_text)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
