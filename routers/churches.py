from fastapi import APIRouter, Depends, HTTPException

from db import get_cursor
from dependencies import get_current_user
from schemas.churches import ChurchResponse, ChurchUpdate

router = APIRouter(prefix="/api/v1/churches", tags=["교회 관리"])


@router.get("/me", response_model=ChurchResponse)
def get_my_church(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT id, name, address, phone, founded_date, denomination, plan, currency, created_at
               FROM shalenu_churches
               WHERE id = %s""",
            (church_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="교회 정보를 찾을 수 없습니다")

    return ChurchResponse(
        id=str(row["id"]),
        name=row["name"],
        address=row.get("address"),
        phone=row.get("phone"),
        founded_at=row.get("founded_date"),
        denomination=row.get("denomination"),
        plan=row["plan"],
        currency=row.get("currency", "KRW"),
        created_at=str(row["created_at"]),
    )


@router.put("/me", response_model=ChurchResponse)
def update_my_church(
    body: ChurchUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    raw = body.model_dump(exclude_unset=True)
    # founded_at → founded_date (DB 컬럼명 매핑)
    if "founded_at" in raw:
        raw["founded_date"] = raw.pop("founded_at")
    allowed = {"name", "address", "phone", "founded_date", "denomination", "currency"}
    updates = {k: v for k, v in raw.items() if k in allowed}

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_churches SET {set_clause}
                WHERE id = %s
                RETURNING id, name, address, phone, founded_date, denomination, plan, currency, created_at""",
            values,
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="교회 정보를 찾을 수 없습니다")

    return ChurchResponse(
        id=str(row["id"]),
        name=row["name"],
        address=row.get("address"),
        phone=row.get("phone"),
        founded_at=row.get("founded_date"),
        denomination=row.get("denomination"),
        plan=row["plan"],
        currency=row.get("currency", "KRW"),
        created_at=str(row["created_at"]),
    )
