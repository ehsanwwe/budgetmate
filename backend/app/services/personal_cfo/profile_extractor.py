from __future__ import annotations

import json
from typing import Any

from app.services.ai import get_ai_chat_completion


async def extract_soft_profile_signals(message: str) -> list[dict[str, Any]]:
    messages = [
        {
            "role": "system",
            "content": (
                "Extract only finance-relevant persona or behavior signals from the Persian message. "
                "Return strict JSON array. Do not include secrets, unrelated personal details, or advice."
            ),
        },
        {"role": "user", "content": message[:1000]},
    ]
    try:
        raw = await get_ai_chat_completion(messages, require_json=True)
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]
    except Exception:
        return []
