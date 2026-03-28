from fastapi import APIRouter, Depends, HTTPException, Query, status

from db import get_cursor
from dependencies import get_current_user
from schemas.finance import (
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    FinanceSummaryResponse,
    MonthlyFinanceStat,
    MonthlyDetailStat,
    CategoryStat,
    BudgetResponse,
    BudgetItemResponse,
)

router = APIRouter(prefix="/api/v1/finance", tags=["재정 관리"])


# --- 재정 요약 리포트 ---


@router.get("/reports/summary", response_model=FinanceSummaryResponse)
def finance_summary(
    year: int = Query(..., description="조회 연도"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # 해당 연도 월별 수입/지출
        cur.execute(
            """SELECT EXTRACT(MONTH FROM txn_date)::int AS month,
                      COALESCE(SUM(CASE WHEN txn_type = 'income' THEN amount ELSE 0 END), 0)::bigint AS income,
                      COALESCE(SUM(CASE WHEN txn_type = 'expense' THEN amount ELSE 0 END), 0)::bigint AS expense
               FROM shalenu_transactions
               WHERE church_id = %s
                 AND EXTRACT(YEAR FROM txn_date) = %s
               GROUP BY month
               ORDER BY month""",
            (church_id, year),
        )
        rows = cur.fetchall()

        # 전체 잔액 (모든 기간)
        cur.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN txn_type = 'income' THEN amount ELSE 0 END), 0)::bigint AS total_income,
                 COALESCE(SUM(CASE WHEN txn_type = 'expense' THEN amount ELSE 0 END), 0)::bigint AS total_expense
               FROM shalenu_transactions
               WHERE church_id = %s""",
            (church_id,),
        )
        totals = cur.fetchone()

    month_map = {r["month"]: r for r in rows}
    monthly = [
        MonthlyFinanceStat(
            month=m,
            income=month_map[m]["income"] if m in month_map else 0,
            expense=month_map[m]["expense"] if m in month_map else 0,
        )
        for m in range(1, 13)
    ]

    year_income = sum(s.income for s in monthly)
    year_expense = sum(s.expense for s in monthly)
    current_balance = totals["total_income"] - totals["total_expense"]

    return FinanceSummaryResponse(
        year=year,
        total_income=year_income,
        total_expense=year_expense,
        current_balance=current_balance,
        monthly=monthly,
    )


@router.get("/reports/monthly", response_model=list[MonthlyDetailStat])
def monthly_report(
    year: int = Query(..., description="조회 연도"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT EXTRACT(MONTH FROM txn_date)::int AS month,
                      COALESCE(SUM(CASE WHEN txn_type = 'income' THEN amount ELSE 0 END), 0)::bigint AS income,
                      COALESCE(SUM(CASE WHEN txn_type = 'expense' THEN amount ELSE 0 END), 0)::bigint AS expense
               FROM shalenu_transactions
               WHERE church_id = %s AND EXTRACT(YEAR FROM txn_date) = %s
               GROUP BY month
               ORDER BY month""",
            (church_id, year),
        )
        rows = cur.fetchall()

    month_map = {r["month"]: r for r in rows}
    return [
        MonthlyDetailStat(
            month=m,
            income=month_map[m]["income"] if m in month_map else 0,
            expense=month_map[m]["expense"] if m in month_map else 0,
            net=(month_map[m]["income"] - month_map[m]["expense"]) if m in month_map else 0,
        )
        for m in range(1, 13)
    ]


@router.get("/reports/by-category", response_model=list[CategoryStat])
def category_report(
    year: int = Query(..., description="조회 연도"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT COALESCE(lc.label, t.category) AS category,
                      COALESCE(SUM(t.amount), 0)::bigint AS total
               FROM shalenu_transactions t
               LEFT JOIN shalenu_lookup_codes lc
                 ON lc.church_id = t.church_id AND lc.category = 'transaction_category' AND lc.code = t.category
               WHERE t.church_id = %s AND EXTRACT(YEAR FROM t.txn_date) = %s
               GROUP BY COALESCE(lc.label, t.category), lc.sort_order
               ORDER BY lc.sort_order NULLS LAST""",
            (church_id, year),
        )
        rows = cur.fetchall()

    return [CategoryStat(category=r["category"], total=r["total"]) for r in rows]


# --- 예산 조회 ---


@router.get("/budgets/{year}", response_model=BudgetResponse)
def get_budget(
    year: int,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # 예산 헤더 조회
        cur.execute(
            """SELECT id, fiscal_year, status, total_amount, approved_by
               FROM shalenu_budgets
               WHERE church_id = %s AND fiscal_year = %s""",
            (church_id, year),
        )
        budget = cur.fetchone()

        if not budget:
            raise HTTPException(status_code=404, detail="해당 연도의 예산을 찾을 수 없습니다")

        budget_id = str(budget["id"])

        # 예산 항목 조회 (lookup_codes JOIN으로 카테고리 이름 포함)
        cur.execute(
            """SELECT bi.id, bi.category, bi.description, bi.planned_amount,
                      COALESCE(lc.label, bi.category) AS category_name
               FROM shalenu_budget_items bi
               LEFT JOIN shalenu_lookup_codes lc
                 ON lc.church_id = %s AND lc.category = 'transaction_category' AND lc.code = bi.category
               WHERE bi.budget_id = %s
               ORDER BY lc.sort_order NULLS LAST, bi.category""",
            (church_id, budget_id),
        )
        item_rows = cur.fetchall()

        # 해당 연도 거래 내역에서 카테고리별 실제 지출/수입 집계
        cur.execute(
            """SELECT category,
                      COALESCE(SUM(amount), 0)::bigint AS actual
               FROM shalenu_transactions
               WHERE church_id = %s AND EXTRACT(YEAR FROM txn_date) = %s
               GROUP BY category""",
            (church_id, year),
        )
        actual_rows = cur.fetchall()

    actual_map = {r["category"]: r["actual"] for r in actual_rows}

    items = [
        BudgetItemResponse(
            id=str(r["id"]),
            category=r["category"],
            category_name=r["category_name"],
            description=r.get("description"),
            planned_amount=int(r["planned_amount"]),
            actual_amount=int(actual_map.get(r["category"], 0)),
        )
        for r in item_rows
    ]

    return BudgetResponse(
        id=budget_id,
        fiscal_year=budget["fiscal_year"],
        status=budget["status"],
        total_planned=sum(i.planned_amount for i in items),
        total_actual=sum(i.actual_amount for i in items),
        approved_by=str(budget["approved_by"]) if budget.get("approved_by") else None,
        items=items,
    )


# --- 거래 내역 CRUD ---


@router.get("/transactions")
def list_transactions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    txn_type: str = Query(None, description="income 또는 expense"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    offset = (page - 1) * size

    with get_cursor() as cur:
        where = "WHERE church_id = %s"
        params: list = [church_id]

        if txn_type:
            where += " AND txn_type = %s"
            params.append(txn_type)

        cur.execute(f"SELECT COUNT(*) AS cnt FROM shalenu_transactions {where}", params)
        total = cur.fetchone()["cnt"]

        cur.execute(
            f"""SELECT id, txn_type, category, amount, description, txn_date,
                       account_id, created_by, created_at
                FROM shalenu_transactions {where}
                ORDER BY txn_date DESC, created_at DESC
                LIMIT %s OFFSET %s""",
            params + [size, offset],
        )
        rows = cur.fetchall()

    items = [_to_response(r) for r in rows]
    return {"items": items, "total": total, "page": page, "size": size}


@router.post(
    "/transactions",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction(
    body: TransactionCreate, current_user: dict = Depends(get_current_user)
):
    church_id = current_user["church_id"]
    user_id = current_user["user_id"]

    if body.txn_type not in ("income", "expense"):
        raise HTTPException(
            status_code=400, detail="txn_type은 income 또는 expense여야 합니다"
        )

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO shalenu_transactions
               (church_id, txn_type, category, amount, description, txn_date, account_id, ref_offering_id, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, txn_type, category, amount, description, txn_date,
                         account_id, created_by, created_at""",
            (
                church_id,
                body.txn_type,
                body.category,
                body.amount,
                body.description,
                body.txn_date,
                body.account_id,
                body.ref_offering_id,
                user_id,
            ),
        )
        row = cur.fetchone()

    return _to_response(row)


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: str, current_user: dict = Depends(get_current_user)
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT id, txn_type, category, amount, description, txn_date,
                      account_id, created_by, created_at
               FROM shalenu_transactions WHERE id = %s AND church_id = %s""",
            (transaction_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="거래 내역을 찾을 수 없습니다")
    return _to_response(row)


@router.put("/transactions/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    allowed_columns = {"txn_type", "category", "amount", "description", "txn_date", "account_id"}
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in allowed_columns}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    if "txn_type" in updates and updates["txn_type"] not in ("income", "expense"):
        raise HTTPException(
            status_code=400, detail="txn_type은 income 또는 expense여야 합니다"
        )

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [transaction_id, church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_transactions SET {set_clause}
                WHERE id = %s AND church_id = %s
                RETURNING id, txn_type, category, amount, description, txn_date,
                          account_id, created_by, created_at""",
            values,
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="거래 내역을 찾을 수 없습니다")
    return _to_response(row)


@router.delete("/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(
    transaction_id: str, current_user: dict = Depends(get_current_user)
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM shalenu_transactions WHERE id = %s AND church_id = %s RETURNING id",
            (transaction_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="거래 내역을 찾을 수 없습니다")


def _to_response(row: dict) -> TransactionResponse:
    return TransactionResponse(
        id=str(row["id"]),
        txn_type=row["txn_type"],
        category=row.get("category"),
        amount=row["amount"],
        description=row.get("description"),
        txn_date=row["txn_date"],
        account_id=str(row["account_id"]) if row.get("account_id") else None,
        created_by=str(row["created_by"]) if row.get("created_by") else None,
        created_at=str(row["created_at"]),
    )
