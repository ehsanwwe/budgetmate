from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.billing import TokenUsageLog
from app.schemas.billing import (
    WalletOut, UsageResponse, UsageLogOut, PlansResponse,
    TokenPackOut, SubscriptionPlanOut, PurchaseRequest, PurchaseResult,
)
from app.services.billing import (
    ensure_wallet, purchase_token_pack, purchase_subscription,
)
from app.services.billing_plans import TOKEN_PACKS, SUBSCRIPTION_PLANS

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/wallet", response_model=WalletOut)
def get_wallet(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallet = ensure_wallet(db, current_user.id)
    return wallet


@router.get("/usage", response_model=UsageResponse)
def get_usage(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total = db.query(TokenUsageLog).filter(TokenUsageLog.user_id == current_user.id).count()
    logs = (
        db.query(TokenUsageLog)
        .filter(TokenUsageLog.user_id == current_user.id)
        .order_by(TokenUsageLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return UsageResponse(
        logs=[UsageLogOut.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/plans", response_model=PlansResponse)
def get_plans():
    return PlansResponse(
        token_packs=[TokenPackOut(**p) for p in TOKEN_PACKS],
        subscription_plans=[SubscriptionPlanOut(**p) for p in SUBSCRIPTION_PLANS],
    )


@router.post("/purchase-token-pack", response_model=PurchaseResult)
def buy_token_pack(
    body: PurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        wallet, purchase = purchase_token_pack(db, current_user.id, body.plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="بسته توکن انتخابی یافت نشد")
    return PurchaseResult(
        wallet=WalletOut.model_validate(wallet),
        tokens_added=purchase.tokens_added,
        plan_id=purchase.plan_id,
        title=purchase.title,
        amount_toman=purchase.amount_toman,
    )


@router.post("/purchase-subscription", response_model=PurchaseResult)
def buy_subscription(
    body: PurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        wallet, purchase, _sub = purchase_subscription(db, current_user.id, body.plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="پلان اشتراک انتخابی یافت نشد")
    return PurchaseResult(
        wallet=WalletOut.model_validate(wallet),
        tokens_added=purchase.tokens_added,
        plan_id=purchase.plan_id,
        title=purchase.title,
        amount_toman=purchase.amount_toman,
    )
