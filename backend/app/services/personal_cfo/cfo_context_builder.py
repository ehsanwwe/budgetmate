from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.personal_cfo.behavior_service import serialize_behavior_insights_for_agent
from app.services.personal_cfo.memory_service import serialize_memories_for_agent
from app.services.personal_cfo.persona_service import serialize_persona_for_agent


def build_cfo_context(db: Session, user_id: int) -> dict:
    return {
        "persona": serialize_persona_for_agent(db, user_id),
        "memories": serialize_memories_for_agent(db, user_id),
        "behavior_insights": serialize_behavior_insights_for_agent(db, user_id),
    }
