from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.personal_cfo import FinancialPersona, PersonaUpdateLog


def get_or_create_persona(db: Session, user_id: int) -> FinancialPersona:
    persona = db.query(FinancialPersona).filter(FinancialPersona.user_id == user_id).first()
    if persona:
        return persona
    persona = FinancialPersona(user_id=user_id, confidence=0, notes_json={})
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona


def update_persona_from_signal(db: Session, user_id: int, signal: dict[str, Any]) -> FinancialPersona:
    persona = get_or_create_persona(db, user_id)
    previous = _persona_snapshot(persona)
    confidence = float(signal.get("confidence") or 0)
    changed = False

    if signal.get("debt_sensitivity") and confidence >= 0.65:
        persona.debt_sensitivity = str(signal["debt_sensitivity"])
        changed = True
    if signal.get("financial_anxiety_level") and confidence >= 0.65:
        persona.financial_anxiety_level = str(signal["financial_anxiety_level"])
        changed = True
    if signal.get("emotional_spending_trigger") and confidence >= 0.65:
        triggers = persona.emotional_spending_triggers_json or []
        if isinstance(triggers, dict):
            triggers = list(triggers.values())
        trigger = str(signal["emotional_spending_trigger"])
        if trigger not in triggers:
            triggers.append(trigger)
            persona.emotional_spending_triggers_json = triggers
            changed = True
    if changed:
        persona.confidence = max(float(persona.confidence or 0), confidence)
        db.add(
            PersonaUpdateLog(
                user_id=user_id,
                previous_json=previous,
                new_json=_persona_snapshot(persona),
                reason=str(signal.get("reason") or "chat_signal"),
                confidence=confidence,
            )
        )
        db.commit()
        db.refresh(persona)
    return persona


def serialize_persona_for_agent(db: Session, user_id: int) -> dict[str, Any]:
    persona = get_or_create_persona(db, user_id)
    return {
        "financial_literacy_level": persona.financial_literacy_level,
        "risk_tolerance": persona.risk_tolerance,
        "financial_anxiety_level": persona.financial_anxiety_level,
        "decision_style": persona.decision_style,
        "time_horizon": persona.time_horizon,
        "debt_sensitivity": persona.debt_sensitivity,
        "discipline_score": persona.discipline_score,
        "saving_preference": persona.saving_preference,
        "emotional_spending_triggers": persona.emotional_spending_triggers_json or [],
        "confidence": persona.confidence,
    }


def _persona_snapshot(persona: FinancialPersona) -> dict[str, Any]:
    return {
        "debt_sensitivity": persona.debt_sensitivity,
        "financial_anxiety_level": persona.financial_anxiety_level,
        "emotional_spending_triggers_json": persona.emotional_spending_triggers_json,
        "confidence": persona.confidence,
    }
