from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class AttendanceEntry(BaseModel):
    member_id: str
    status: str = "present"
    note: Optional[str] = None


class AttendanceBatchCreate(BaseModel):
    service_id: Optional[str] = None
    attendance_date: date
    entries: List[AttendanceEntry]


class AttendanceResponse(BaseModel):
    id: str
    member_id: str
    member_name: Optional[str] = None
    service_id: Optional[str] = None
    service_name: Optional[str] = None
    attendance_date: date
    status: str
    note: Optional[str] = None


class AttendanceStatsResponse(BaseModel):
    total_services: int
    avg_attendance: float
    by_service: List[dict]
    monthly: List[dict]
