from pydantic import BaseModel
from typing import Optional
from datetime import date


class BirthdayMember(BaseModel):
    id: str
    name: str
    birth_date: date
    phone: Optional[str] = None
    email: Optional[str] = None
    days_until: int


class BirthdaySettingsUpdate(BaseModel):
    alert_days_before: Optional[int] = None
    is_active: Optional[bool] = None
    notify_via: Optional[str] = None


class BirthdaySettingsResponse(BaseModel):
    id: Optional[str] = None
    alert_days_before: int = 7
    is_active: bool = True
    notify_via: str = "both"
