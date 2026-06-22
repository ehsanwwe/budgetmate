"""Builds natural-language conversation context blocks for LLM consumption.

Splits full history into older context and recent exchange sections, preserving
financially relevant statements from earlier in the conversation. Used by both
SemanticInterpreter and AgentPlanner so the LLM can resolve references like
'هزینه‌های بالا', 'اول چت گفتم', 'همون چیزایی که گفتم'.
"""
from __future__ import annotations


def build_history_context(
    history: list[dict],
    recent_count: int = 12,
    max_chars_recent: int = 1200,
    max_chars_older: int = 800,
) -> str:
    """Format conversation history as a labeled natural-language block.

    Returns two sections:
    - EARLIER CONVERSATION: messages beyond recent_count (more compressed)
    - RECENT EXCHANGE: the last recent_count messages (fuller detail)
    """
    if not history:
        return "(no prior context)"

    valid = [m for m in history if m.get("role") in {"user", "assistant"} and m.get("content")]
    if not valid:
        return "(no prior context)"

    older = valid[:-recent_count] if len(valid) > recent_count else []
    recent = valid[-recent_count:] if len(valid) > recent_count else valid

    lines: list[str] = []

    if older:
        lines.append("── EARLIER CONVERSATION (key facts from earlier in this chat) ──")
        for item in older:
            label = "USER" if item["role"] == "user" else "ASSISTANT"
            text = str(item["content"])[:max_chars_older]
            lines.append(f"[{label}]: {text}")
        lines.append("")

    lines.append("── RECENT EXCHANGE ──")
    for item in recent:
        label = "USER" if item["role"] == "user" else "ASSISTANT"
        text = str(item["content"])[:max_chars_recent]
        lines.append(f"[{label}]: {text}")

    return "\n".join(lines)
