from pydantic import BaseModel
from typing import Optional
from datetime import time


class WorshipServiceCreate(BaseModel):
    name: str
    day_of_week: Optional[int] = None
    start_time: Optional[time] = None
    sort_order: int = 0


class WorshipServiceUpdate(BaseModel):
    name: Optional[str] = None
    day_of_week: Optional[int] = None
    start_time: Optional[time] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class WorshipServiceResponse(BaseModel):
    id: str
    name: str
    day_of_week: Optional[int] = None
    start_time: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: str
