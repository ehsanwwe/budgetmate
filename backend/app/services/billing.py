from __future__ import annotations

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.billing import TokenPurchase, TokenUsageLog, TokenWallet, UserSubscription
from app.services.billing_plans import get_subscription_plan, get_token_pack


INSUFFICIENT_TOKENS_MESSAGE = "اعتبار توکن شما کافی نیست. برای ادامه گفت‌وگو، از بخش خرید توکن یا خرید اشتراک اعتبار خود را افزایش دهید."


def ensure_wallet(db: Session, user_id: int) -> TokenWallet:
    wallet = db.query(TokenWallet).filter(TokenWallet.user_id == user_id).first()
    if wallet:
        return wallet

    wallet = TokenWallet(
        user_id=user_id,
        balance_tokens=settings.STARTER_FREE_TOKENS,
        total_granted_tokens=settings.STARTER_FREE_TOKENS,
        total_purchased_tokens=0,
        total_consumed_tokens=0,
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


def has_chat_credit(db: Session, user_id: int, estimated_prompt_tokens: int) -> bool:
    wallet = ensure_wallet(db, user_id)
    return wallet.balance_tokens > 0 and wallet.balance_tokens >= estimated_prompt_tokens


def consume_chat_tokens(
    db: Session,
    user_id: int,
    usage: dict[str, int],
    chat_message_id: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    meta: dict | None = None,
) -> TokenUsageLog:
    wallet = ensure_wallet(db, user_id)
    total_tokens = max(0, int(usage.get("total_tokens") or 0))
    balance_before = wallet.balance_tokens
    balance_after = max(0, balance_before - total_tokens)

    wallet.balance_tokens = balance_after
    wallet.total_consumed_tokens += total_tokens
    wallet.updated_at = datetime.utcnow()

    log = TokenUsageLog(
        user_id=user_id,
        chat_message_id=chat_message_id,
        provider=provider,
        model=model,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        total_tokens=total_tokens,
        balance_before=balance_before,
        balance_after=balance_after,
        reason="chat",
        meta=meta,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def purchase_token_pack(db: Session, user_id: int, plan_id: str) -> tuple[TokenWallet, TokenPurchase]:
    plan = get_token_pack(plan_id)
    if not plan:
        raise ValueError("invalid_plan")

    wallet = ensure_wallet(db, user_id)
    tokens = int(plan["tokens"])
    wallet.balance_tokens += tokens
    wallet.total_purchased_tokens += tokens
    wallet.updated_at = datetime.utcnow()

    purchase = TokenPurchase(
        user_id=user_id,
        kind="token_pack",
        plan_id=plan["plan_id"],
        title=plan["title"],
        amount_toman=plan["amount_toman"],
        tokens_added=tokens,
        status="mock_paid",
        meta={"mock": True},
    )
    db.add(purchase)
    db.commit()
    db.refresh(wallet)
    db.refresh(purchase)
    return wallet, purchase


def purchase_subscription(db: Session, user_id: int, plan_id: str) -> tuple[TokenWallet, TokenPurchase, UserSubscription]:
    plan = get_subscription_plan(plan_id)
    if not plan:
        raise ValueError("invalid_plan")

    now = datetime.utcnow()
    tokens = int(plan["monthly_token_quota"])
    wallet = ensure_wallet(db, user_id)
    wallet.balance_tokens += tokens
    wallet.total_purchased_tokens += tokens
    wallet.updated_at = now

    existing = db.query(UserSubscription).filter(
        UserSubscription.user_id == user_id,
        UserSubscription.status == "active",
    ).first()
    if existing:
        existing.status = "expired"

    subscription = UserSubscription(
        user_id=user_id,
        plan_id=plan["plan_id"],
        title=plan["title"],
        status="active",
        starts_at=now,
        ends_at=now + timedelta(days=30),
        monthly_token_quota=tokens,
        tokens_granted=tokens,
    )
    purchase = TokenPurchase(
        user_id=user_id,
        kind="subscription",
        plan_id=plan["plan_id"],
        title=plan["title"],
        amount_toman=plan["amount_toman"],
        tokens_added=tokens,
        status="mock_paid",
        meta={"mock": True},
    )
    db.add(subscription)
    db.add(purchase)
    db.commit()
    db.refresh(wallet)
    db.refresh(purchase)
    db.refresh(subscription)
    return wallet, purchase, subscription
