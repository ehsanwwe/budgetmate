from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.personal_cfo import BehaviorInsight
from app.services.personal_cfo.memory_service import create_memory
from app.services.personal_cfo.persona_service import update_persona_from_signal

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_text(message: str) -> str:
    return " ".join(message.translate(_DIGIT_MAP).replace("\u200c", " ").split())

ALLOWED_INSIGHTS = {
    "emotional_spending",
    "sadness_spending",
    "stress_spending",
    "impulse_purchase",
    "end_of_month_overspending",
    "avoidance_behavior",
    "high_transport_spending",
    "high_food_spending",
    "income_instability",
    "low_saving_rate",
    "improving_discipline",
    "debt_anxiety",
    "liquidity_pressure",
}


def detect_basic_behavior_signals(
    db: Session,
    user_id: int,
    latest_message: str,
    latest_operations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    text = normalize_text(latest_message)
    signals: list[dict[str, Any]] = []
    if "استرس" in text and ("خرید" in text or "خرج" in text):
        signals.append({"insight_type": "stress_spending", "confidence": 0.78, "memory_type": "behavioral_trigger", "title": "خرج هنگام استرس", "persona": {"emotional_spending_trigger": "stress", "confidence": 0.78, "reason": "stress_spending_phrase"}})
    if "آخر ماه" in text and ("کم میارم" in text or "کم می آورم" in text or "پول کم" in text):
        signals.append({"insight_type": "liquidity_pressure", "confidence": 0.76, "memory_type": "constraint", "title": "کمبود نقدینگی آخر ماه"})
        signals.append({"insight_type": "end_of_month_overspending", "confidence": 0.7, "memory_type": "expense_pattern", "title": "فشار مالی آخر ماه"})
    if "بدهی" in text and ("میترسم" in text or "می ترسم" in text or "نگران" in text):
        signals.append({"insight_type": "debt_anxiety", "confidence": 0.82, "memory_type": "risk_note", "title": "حساسیت نسبت به بدهی", "persona": {"debt_sensitivity": "high", "financial_anxiety_level": "medium", "confidence": 0.82, "reason": "debt_fear_phrase"}})
    if ("میخوام" in text or "می خواهم" in text or "میخوام" in text) and ("پس انداز" in text or "پس‌انداز" in text) and any(word in text for word in ("ماشین", "خانه", "لپ تاپ", "سفر")):
        signals.append({"insight_type": None, "confidence": 0.72, "memory_type": "goal", "title": "هدف پس انداز کاربر"})

    saved: list[dict[str, Any]] = []
    for signal in signals:
        if signal.get("insight_type"):
            upsert_behavior_insight(
                db,
                user_id,
                signal["insight_type"],
                {"message": latest_message, "operations": latest_operations or []},
                signal["confidence"],
            )
        if signal.get("memory_type"):
            create_memory(
                db,
                user_id,
                signal["memory_type"],
                signal["title"],
                {"message": latest_message},
                source="chat",
                confidence=signal["confidence"],
            )
        if signal.get("persona"):
            update_persona_from_signal(db, user_id, signal["persona"])
        saved.append(signal)
    return saved


def upsert_behavior_insight(
    db: Session,
    user_id: int,
    insight_type: str,
    evidence: dict[str, Any],
    confidence: float,
) -> BehaviorInsight:
    if insight_type not in ALLOWED_INSIGHTS:
        raise ValueError("unsupported insight type")
    insight = db.query(BehaviorInsight).filter(
        BehaviorInsight.user_id == user_id,
        BehaviorInsight.insight_type == insight_type,
    ).first()
    now = datetime.utcnow()
    if insight:
        insight.evidence_json = evidence
        insight.confidence = max(float(insight.confidence or 0), max(0, min(float(confidence), 1)))
        insight.last_detected_at = now
        insight.is_active = True
    else:
        insight = BehaviorInsight(
            user_id=user_id,
            insight_type=insight_type,
            evidence_json=evidence,
            confidence=max(0, min(float(confidence), 1)),
            first_detected_at=now,
            last_detected_at=now,
            is_active=True,
        )
        db.add(insight)
    db.commit()
    db.refresh(insight)
    return insight


def serialize_behavior_insights_for_agent(db: Session, user_id: int) -> list[dict[str, Any]]:
    rows = db.query(BehaviorInsight).filter(
        BehaviorInsight.user_id == user_id,
        BehaviorInsight.is_active == True,
    ).order_by(BehaviorInsight.last_detected_at.desc()).limit(8).all()
    return [
        {
            "insight_type": row.insight_type,
            "confidence": row.confidence,
            "evidence": row.evidence_json,
        }
        for row in rows
    ]
