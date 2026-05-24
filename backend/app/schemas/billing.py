from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class WalletOut(BaseModel):
    balance_tokens: int
    total_granted_tokens: int
    total_purchased_tokens: int
    total_consumed_tokens: int
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UsageLogOut(BaseModel):
    id: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    balance_before: int
    balance_after: int
    reason: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UsageResponse(BaseModel):
    logs: List[UsageLogOut]
    total: int
    page: int
    page_size: int


class TokenPackOut(BaseModel):
    plan_id: str
    title: str
    tokens: int
    amount_toman: int


class SubscriptionPlanOut(BaseModel):
    plan_id: str
    title: str
    monthly_token_quota: int
    amount_toman: int
    benefits: List[str] = []


class PlansResponse(BaseModel):
    token_packs: List[TokenPackOut]
    subscription_plans: List[SubscriptionPlanOut]


class PurchaseRequest(BaseModel):
    plan_id: str


class PurchaseResult(BaseModel):
    wallet: WalletOut
    tokens_added: int
    plan_id: str
    title: str
    amount_toman: int
