from pydantic import BaseModel
from typing import Optional


class LookupCreate(BaseModel):
    category: str  # 'offering_type' | 'worship_type' | 'budget_category' | 'budget_item_template'
    code: str
    label: str
    sort_order: int = 0
    parent_code: Optional[str] = None


class LookupUpdate(BaseModel):
    label: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class LookupResponse(BaseModel):
    id: str
    category: str
    code: str
    value: str  # code와 동일 (프론트엔드 호환)
    label: str
    name: str  # label과 동일 (프론트엔드 호환)
    sort_order: int
    is_active: bool
    parent_code: Optional[str] = None
