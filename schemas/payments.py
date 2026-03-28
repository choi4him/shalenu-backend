from pydantic import BaseModel
from typing import Optional


class PaymentLinkCreate(BaseModel):
    title: str
    description: Optional[str] = None
    amount: Optional[int] = None  # 센트/원 단위, None이면 기부자가 직접 입력
    currency: str = "usd"          # "usd" → Stripe, "krw" → PortOne


class KoreaPaymentLinkCreate(BaseModel):
    title: str
    description: Optional[str] = None
    amount: Optional[int] = None   # 원 단위 (None이면 기부자 자유 입력 — PortOne 지원 시)


class PaymentLinkResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    amount: Optional[int] = None
    currency: str
    provider: str = "stripe"
    stripe_price_id: Optional[str] = None
    stripe_link_id: Optional[str] = None
    stripe_link_url: Optional[str] = None
    portone_link_id: Optional[str] = None
    portone_link_url: Optional[str] = None
    is_active: bool
    created_at: str


class OnlinePaymentResponse(BaseModel):
    id: str
    payment_link_id: Optional[str] = None
    link_title: Optional[str] = None
    donor_name: Optional[str] = None
    donor_email: Optional[str] = None
    amount: int
    currency: str
    status: str
    paid_at: Optional[str] = None
    created_at: str
