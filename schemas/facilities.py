from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FacilityCreate(BaseModel):
    name: str
    capacity: Optional[int] = None
    description: Optional[str] = None


class FacilityUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class FacilityResponse(BaseModel):
    id: str
    name: str
    capacity: Optional[int] = None
    description: Optional[str] = None
    is_active: bool
    created_at: str


class BookingCreate(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    note: Optional[str] = None


class BookingStatusUpdate(BaseModel):
    status: str  # approved, cancelled


class BookingResponse(BaseModel):
    id: str
    facility_id: str
    facility_name: Optional[str] = None
    title: str
    booked_by: str
    booked_by_name: Optional[str] = None
    start_time: str
    end_time: str
    status: str
    note: Optional[str] = None
    created_at: str
