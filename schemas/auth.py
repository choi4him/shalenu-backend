from pydantic import BaseModel
from typing import Optional
from datetime import date


class RegisterRequest(BaseModel):
    church_name: str
    email: str
    password: str
    name: str
    church_address: Optional[str] = None
    church_phone: Optional[str] = None
    founded_date: Optional[date] = None
    denomination: Optional[str] = None
    admin_role: str = "admin"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    church_id: str
    email: str
    name: Optional[str] = None
    role: str
