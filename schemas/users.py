from pydantic import BaseModel
from typing import Optional


class UserListItem(BaseModel):
    id: str
    full_name: Optional[str] = None
    email: str
    role: str
    is_active: bool


class UserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
