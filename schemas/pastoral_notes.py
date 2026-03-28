from pydantic import BaseModel
from typing import Optional
from datetime import date


class PastoralNoteCreate(BaseModel):
    member_id: str
    category: str = "general"  # visit, counsel, prayer, general
    content: str
    is_private: bool = True
    visited_at: Optional[date] = None


class PastoralNoteUpdate(BaseModel):
    category: Optional[str] = None
    content: Optional[str] = None
    is_private: Optional[bool] = None
    visited_at: Optional[date] = None


class PastoralNoteResponse(BaseModel):
    id: str
    member_id: str
    member_name: Optional[str] = None
    author_id: str
    author_name: Optional[str] = None
    category: str
    content: str
    is_private: bool
    visited_at: Optional[date] = None
    created_at: str
    updated_at: str
