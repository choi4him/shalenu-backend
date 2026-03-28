from pydantic import BaseModel
from typing import Optional
from datetime import date


class GroupCreate(BaseModel):
    name: str
    group_type: Optional[str] = None
    leader_id: Optional[str] = None
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    group_type: Optional[str] = None
    leader_id: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class GroupResponse(BaseModel):
    id: str
    name: str
    group_type: Optional[str] = None
    leader_id: Optional[str] = None
    leader_name: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    member_count: int = 0
    created_at: str


class GroupMemberAdd(BaseModel):
    member_id: str
    role: str = "member"


class GroupMemberResponse(BaseModel):
    id: str
    member_id: str
    member_name: str
    role: str
    joined_at: Optional[date] = None
    is_active: bool
