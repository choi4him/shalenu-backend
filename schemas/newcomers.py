from pydantic import BaseModel
from typing import Optional
from datetime import date


class NewcomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    visit_date: date
    visit_route: Optional[str] = None
    assigned_to: Optional[str] = None
    note: Optional[str] = None


class NewcomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    visit_date: Optional[date] = None
    visit_route: Optional[str] = None
    assigned_to: Optional[str] = None
    note: Optional[str] = None


class NewcomerStatusUpdate(BaseModel):
    status: str


class NewcomerResponse(BaseModel):
    id: str
    member_id: Optional[str] = None
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    address: Optional[str] = None
    visit_date: date
    visit_route: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    status: str
    note: Optional[str] = None
    created_at: str
