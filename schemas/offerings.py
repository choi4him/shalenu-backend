from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class OfferingItemCreate(BaseModel):
    member_id: Optional[str] = None
    member_name: Optional[str] = None
    amount: int
    payment_method: str = "cash"
    notes: Optional[str] = None


class OfferingCreate(BaseModel):
    offering_date: date
    offering_type_code: str
    worship_type_code: str
    status: str = "confirmed"
    items: List[OfferingItemCreate]


class OfferingItemResponse(BaseModel):
    id: str
    offering_id: str
    member_id: Optional[str] = None
    member_name: Optional[str] = None
    amount: int
    payment_method: str
    notes: Optional[str] = None


class OfferingResponse(BaseModel):
    id: str
    offering_date: date
    offering_type_code: str
    offering_type_name: Optional[str] = None
    worship_type_code: str
    worship_type_name: Optional[str] = None
    total_amount: int
    status: str
    created_by: Optional[str] = None
    created_at: str
    item_count: Optional[int] = None
    items: Optional[List[OfferingItemResponse]] = None


class OfferingTypeSummary(BaseModel):
    type: str
    type_label: str
    total: int


class MonthlyOfferingItem(BaseModel):
    month: int
    type: str
    amount: int


class OfferingStatsResponse(BaseModel):
    year: int
    grand_total: int
    by_type: List[OfferingTypeSummary]
    monthly: List[MonthlyOfferingItem]


class MemberOfferingStat(BaseModel):
    member_id: Optional[str] = None
    member_name: str
    total: int
    by_type: dict
