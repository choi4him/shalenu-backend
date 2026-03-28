from pydantic import BaseModel
from typing import Optional
from datetime import date


class MemberCreate(BaseModel):
    name: str
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    birth_date: Optional[date] = None
    join_date: Optional[date] = None
    baptism_date: Optional[date] = None
    status: str = "active"


class MemberUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    birth_date: Optional[date] = None
    join_date: Optional[date] = None
    baptism_date: Optional[date] = None
    status: Optional[str] = None


class MemberResponse(BaseModel):
    id: str
    name: str
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    birth_date: Optional[date] = None
    join_date: Optional[date] = None
    baptism_date: Optional[date] = None
    status: str
    created_at: str
