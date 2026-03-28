from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class TransactionCreate(BaseModel):
    txn_type: str  # income | expense
    category: str
    amount: int
    description: str
    txn_date: date
    account_id: str
    ref_offering_id: Optional[str] = None


class TransactionUpdate(BaseModel):
    txn_type: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[int] = None
    description: Optional[str] = None
    txn_date: Optional[date] = None
    account_id: Optional[str] = None


class TransactionResponse(BaseModel):
    id: str
    txn_type: str
    category: str
    amount: int
    description: str
    txn_date: date
    account_id: str
    created_by: Optional[str] = None
    created_at: str


class MonthlyFinanceStat(BaseModel):
    month: int
    income: int
    expense: int


class FinanceSummaryResponse(BaseModel):
    year: int
    total_income: int
    total_expense: int
    current_balance: int
    monthly: List[MonthlyFinanceStat]


class MonthlyDetailStat(BaseModel):
    month: int
    income: int
    expense: int
    net: int


class CategoryStat(BaseModel):
    category: str
    total: int


class BudgetItemResponse(BaseModel):
    id: str
    category: str
    category_name: Optional[str] = None
    description: Optional[str] = None
    planned_amount: int
    actual_amount: int


class BudgetResponse(BaseModel):
    id: str
    fiscal_year: int
    status: str
    total_planned: int
    total_actual: int
    approved_by: Optional[str] = None
    items: List[BudgetItemResponse]
