from pydantic import BaseModel
from typing import Optional
from datetime import date


class ChurchResponse(BaseModel):
    id: str
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    founded_at: Optional[date] = None
    denomination: Optional[str] = None
    plan: str
    currency: str = "KRW"
    created_at: str


class ChurchUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    founded_at: Optional[date] = None
    denomination: Optional[str] = None
    currency: Optional[str] = None
