from fastapi import APIRouter, Depends, HTTPException, Query, status

from db import get_cursor
from dependencies import get_current_user
from schemas.lookup import LookupCreate, LookupUpdate, LookupResponse

router = APIRouter(prefix="/api/v1/lookup", tags=["공통 코드"])

ALLOWED_CATEGORIES = {
    "offering_type", "worship_type", "transaction_category",
    "account_type", "budget_category", "budget_item_template",
    "group_type",
}


@router.get("/{category}")
def list_lookup(
    category: str,
    parent: str = Query(None, description="부모 코드 필터 (budget_item_template용)"),
    current_user: dict = Depends(get_current_user),
):
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail="유효하지 않은 카테고리입니다")

    church_id = current_user["church_id"]

    with get_cursor() as cur:
        where = "church_id = %s AND category = %s AND is_active = TRUE"
        params: list = [church_id, category]

        if parent:
            where += " AND parent_code = %s"
            params.append(parent)

        cur.execute(
            f"""SELECT id, category, code, label, sort_order, is_active, parent_code
               FROM shalenu_lookup_codes
               WHERE {where}
               ORDER BY sort_order, label""",
            params,
        )
        rows = cur.fetchall()

    return [_to_response(r) for r in rows]


@router.post("", response_model=LookupResponse, status_code=status.HTTP_201_CREATED)
def create_lookup(body: LookupCreate, current_user: dict = Depends(get_current_user)):
    if body.category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail="유효하지 않은 카테고리입니다")

    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # 같은 교회 내 중복 code 방지
        cur.execute(
            "SELECT id FROM shalenu_lookup_codes WHERE church_id = %s AND category = %s AND code = %s",
            (church_id, body.category, body.code),
        )
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="이미 존재하는 코드입니다")

        cur.execute(
            """INSERT INTO shalenu_lookup_codes (church_id, category, code, label, sort_order, parent_code)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id, category, code, label, sort_order, is_active, parent_code""",
            (church_id, body.category, body.code, body.label, body.sort_order, body.parent_code),
        )
        row = cur.fetchone()

    return _to_response(row)


@router.put("/{lookup_id}", response_model=LookupResponse)
def update_lookup(
    lookup_id: str,
    body: LookupUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    allowed_columns = {"label", "sort_order", "is_active"}
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in allowed_columns}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [lookup_id, church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_lookup_codes SET {set_clause}
                WHERE id = %s AND church_id = %s
                RETURNING id, category, code, label, sort_order, is_active, parent_code""",
            values,
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")
    return _to_response(row)


@router.delete("/{lookup_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lookup(lookup_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            "UPDATE shalenu_lookup_codes SET is_active = FALSE WHERE id = %s AND church_id = %s RETURNING id",
            (lookup_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")


def _to_response(row: dict) -> LookupResponse:
    return LookupResponse(
        id=str(row["id"]),
        category=row["category"],
        code=row["code"],
        value=row["code"],
        label=row["label"],
        name=row["label"],
        sort_order=row["sort_order"],
        is_active=row["is_active"],
        parent_code=row.get("parent_code"),
    )
