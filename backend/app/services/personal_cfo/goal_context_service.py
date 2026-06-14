from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from app.models.goal import Goal


_GOAL_SYNONYMS = {
    "لپتاب": "لپتاپ",
    "لپ تاب": "لپتاپ",
    "لپ تاپ": "لپتاپ",
    "لپ باپ": "لپتاپ",
    "لپ‌تاپ": "لپتاپ",
    "لپباپ": "لپتاپ",
    "laptop": "لپتاپ",
}

# Common prefixes stripped from goal titles before semantic comparison.
# Ordered longest-first so "هدف خرید " is tried before "هدف " and "خرید ".
_GOAL_PREFIXES: tuple[str, ...] = (
    "هدف خرید ",
    "هدف پس‌انداز برای ",
    "هدف پس انداز برای ",
    "هدف پس‌انداز ",
    "هدف پس انداز ",
    "هدف ذخیره برای ",
    "هدف ذخیره ",
    "هدف ",
    "خرید ",
    "پس‌انداز برای ",
    "پس انداز برای ",
    "پس‌انداز ",
    "پس انداز ",
    "ذخیره برای ",
    "ذخیره ",
)


def normalize_goal_text(value: str | None) -> str:
    text = str(value or "").lower()
    replacements = {
        "‌": "",
        "ي": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = " ".join(text.split())
    for old, new in _GOAL_SYNONYMS.items():
        text = text.replace(old, new)
    # Strip one matching prefix (longest-first order ensures correct priority)
    for prefix in _GOAL_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):]
            break
    return text.strip()


def goal_match_score(query_text: str, title: str) -> float:
    query = normalize_goal_text(query_text)
    normalized_title = normalize_goal_text(title)
    if not query or not normalized_title:
        return 0
    if query in normalized_title or normalized_title in query:
        return 1.0
    query_tokens = {token for token in query.split() if len(token) > 1}
    title_tokens = {token for token in normalized_title.split() if len(token) > 1}
    if not query_tokens or not title_tokens:
        return SequenceMatcher(None, query, normalized_title).ratio()
    overlap = len(query_tokens.intersection(title_tokens)) / len(query_tokens.union(title_tokens))
    ratio = SequenceMatcher(None, query, normalized_title).ratio()
    return max(overlap, ratio)


def list_active_goals(db: Session, user_id: int, limit: int = 20) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.is_active == True)
        .order_by(Goal.deadline.asc().nullslast(), Goal.id.desc())
        .limit(limit)
        .all()
    )


def find_goal_candidates(db: Session, user_id: int, query_text: str, limit: int = 10) -> list[Goal]:
    goals = list_active_goals(db, user_id, limit=50)
    if not normalize_goal_text(query_text):
        return goals[:limit]
    scored: list[tuple[float, Goal]] = []
    for goal in goals:
        score = goal_match_score(query_text, goal.title or "")
        if score >= 0.45:
            scored.append((score, goal))
    return [goal for _, goal in sorted(scored, key=lambda item: (-item[0], item[1].id))[:limit]]


def serialize_goals_for_agent(db: Session, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for goal in list_active_goals(db, user_id, limit=limit):
        remaining = max(int(goal.target_amount or 0) - int(goal.current_amount or 0), 0)
        payload.append(
            {
                "id": goal.id,
                "title": goal.title,
                "normalized_title": normalize_goal_text(goal.title),
                "target_amount": goal.target_amount,
                "current_amount": goal.current_amount,
                "remaining_amount": remaining,
                "deadline": goal.deadline.isoformat() if goal.deadline else None,
                "status": goal.status,
                "notes": goal.notes_json,
            }
        )
    return payload
