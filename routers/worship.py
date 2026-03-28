from fastapi import APIRouter, Depends, HTTPException, status

from db import get_cursor
from dependencies import get_current_user
from schemas.worship import WorshipServiceCreate, WorshipServiceUpdate, WorshipServiceResponse

router = APIRouter(prefix="/api/v1/worship", tags=["예배 관리"])


def _to_response(row: dict) -> WorshipServiceResponse:
    return WorshipServiceResponse(
        id=str(row["id"]),
        name=row["name"],
        day_of_week=row.get("day_of_week"),
        start_time=str(row["start_time"]) if row.get("start_time") else None,
        is_active=row.get("is_active", True),
        sort_order=row.get("sort_order", 0),
        created_at=str(row["created_at"]),
    )


@router.get("", response_model=list[WorshipServiceResponse])
def list_worship_services(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT id, name, day_of_week, start_time, is_active, sort_order, created_at
               FROM shalenu_worship_services
               WHERE church_id = %s
               ORDER BY sort_order, name""",
            (church_id,),
        )
        rows = cur.fetchall()

    return [_to_response(r) for r in rows]


@router.post("", response_model=WorshipServiceResponse, status_code=status.HTTP_201_CREATED)
def create_worship_service(body: WorshipServiceCreate, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO shalenu_worship_services
               (church_id, name, day_of_week, start_time, sort_order)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, name, day_of_week, start_time, is_active, sort_order, created_at""",
            (church_id, body.name, body.day_of_week, body.start_time, body.sort_order),
        )
        row = cur.fetchone()

    return _to_response(row)


@router.get("/{service_id}", response_model=WorshipServiceResponse)
def get_worship_service(service_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT id, name, day_of_week, start_time, is_active, sort_order, created_at
               FROM shalenu_worship_services
               WHERE id = %s AND church_id = %s""",
            (service_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="예배를 찾을 수 없습니다")
    return _to_response(row)


@router.put("/{service_id}", response_model=WorshipServiceResponse)
def update_worship_service(
    service_id: str,
    body: WorshipServiceUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [service_id, church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_worship_services SET {set_clause}
                WHERE id = %s AND church_id = %s
                RETURNING id, name, day_of_week, start_time, is_active, sort_order, created_at""",
            values,
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="예배를 찾을 수 없습니다")
    return _to_response(row)
