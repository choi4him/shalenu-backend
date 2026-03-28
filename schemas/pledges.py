from pydantic import BaseModel
from typing import Optional


class PledgeCreate(BaseModel):
    member_id: str
    pledge_year: int
    offering_type: str
    pledged_amount: int


class PledgeUpdate(BaseModel):
    pledged_amount: Optional[int] = None
    status: Optional[str] = None


class PledgePayRequest(BaseModel):
    amount: int


class PledgeResponse(BaseModel):
    id: str
    member_id: str
    member_name: Optional[str] = None
    pledge_year: int
    offering_type: str
    offering_type_label: Optional[str] = None
    pledged_amount: int
    paid_amount: int
    status: str
    created_at: str
