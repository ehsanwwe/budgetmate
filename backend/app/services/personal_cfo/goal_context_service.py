from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.goal import Goal


def list_active_goals(db: Session, user_id: int, limit: int = 20) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.is_active == True)
        .order_by(Goal.deadline.asc().nullslast(), Goal.id.desc())
        .limit(limit)
        .all()
    )


def find_goal_candidates(db: Session, user_id: int, query_text: str, limit: int = 10) -> list[Goal]:
    normalized = " ".join((query_text or "").replace("\u200c", " ").split()).lower()
    goals = list_active_goals(db, user_id, limit=50)
    if not normalized:
        return goals[:limit]
    scored: list[tuple[int, Goal]] = []
    query_tokens = {token for token in normalized.split() if len(token) > 1}
    for goal in goals:
        title = (goal.title or "").replace("\u200c", " ").lower()
        score = 0
        if normalized in title or title in normalized:
            score += 5
        score += len(query_tokens.intersection(set(title.split())))
        if score:
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
                "target_amount": goal.target_amount,
                "current_amount": goal.current_amount,
                "remaining_amount": remaining,
                "deadline": goal.deadline.isoformat() if goal.deadline else None,
                "status": goal.status,
                "notes": goal.notes_json,
            }
        )
    return payload
