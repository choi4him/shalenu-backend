from fastapi import APIRouter, Depends, HTTPException, Query, status

from db import get_cursor
from dependencies import get_current_user
from plan_check import require_feature
from schemas.newcomers import NewcomerCreate, NewcomerUpdate, NewcomerStatusUpdate, NewcomerResponse

router = APIRouter(prefix="/api/v1/newcomers", tags=["새가족 관리"], dependencies=[Depends(require_feature("community"))])


COLS = """n.id, n.member_id, n.name, n.phone, n.email, n.gender, n.birth_date,
          n.address, n.visit_date, n.visit_route, n.assigned_to, n.status,
          n.note, n.created_at,
          am.name AS assigned_to_name"""


def _to_response(row: dict) -> NewcomerResponse:
    return NewcomerResponse(
        id=str(row["id"]),
        member_id=str(row["member_id"]) if row.get("member_id") else None,
        name=row["name"],
        phone=row.get("phone"),
        email=row.get("email"),
        gender=row.get("gender"),
        birth_date=row.get("birth_date"),
        address=row.get("address"),
        visit_date=row["visit_date"],
        visit_route=row.get("visit_route"),
        assigned_to=str(row["assigned_to"]) if row.get("assigned_to") else None,
        assigned_to_name=row.get("assigned_to_name"),
        status=row["status"],
        note=row.get("note"),
        created_at=str(row["created_at"]),
    )


@router.get("", response_model=list[NewcomerResponse])
def list_newcomers(
    status_filter: str = Query(None, alias="status", description="상태 필터 (visiting/registered/left)"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    conditions = ["n.church_id = %s"]
    params: list = [church_id]

    if status_filter:
        conditions.append("n.status = %s")
        params.append(status_filter)

    where = " AND ".join(conditions)

    with get_cursor() as cur:
        cur.execute(
            f"""SELECT {COLS}
                FROM shalenu_newcomers n
                LEFT JOIN shalenu_members am ON n.assigned_to = am.id
                WHERE {where}
                ORDER BY n.visit_date DESC""",
            params,
        )
        rows = cur.fetchall()

    return [_to_response(r) for r in rows]


@router.post("", response_model=NewcomerResponse, status_code=status.HTTP_201_CREATED)
def create_newcomer(body: NewcomerCreate, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO shalenu_newcomers
               (church_id, name, phone, email, gender, birth_date, address,
                visit_date, visit_route, assigned_to, note)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, member_id, name, phone, email, gender, birth_date,
                         address, visit_date, visit_route, assigned_to, status,
                         note, created_at""",
            (
                church_id, body.name, body.phone, body.email, body.gender,
                body.birth_date, body.address, body.visit_date, body.visit_route,
                body.assigned_to, body.note,
            ),
        )
        row = cur.fetchone()

        assigned_to_name = None
        if row.get("assigned_to"):
            cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (row["assigned_to"],))
            am = cur.fetchone()
            if am:
                assigned_to_name = am["name"]

    result = dict(row)
    result["assigned_to_name"] = assigned_to_name
    return _to_response(result)


@router.put("/{newcomer_id}", response_model=NewcomerResponse)
def update_newcomer(
    newcomer_id: str,
    body: NewcomerUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [newcomer_id, church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_newcomers SET {set_clause}, updated_at = NOW()
                WHERE id = %s AND church_id = %s
                RETURNING id, member_id, name, phone, email, gender, birth_date,
                          address, visit_date, visit_route, assigned_to, status,
                          note, created_at""",
            values,
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="새가족을 찾을 수 없습니다")

        assigned_to_name = None
        if row.get("assigned_to"):
            cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (row["assigned_to"],))
            am = cur.fetchone()
            if am:
                assigned_to_name = am["name"]

    result = dict(row)
    result["assigned_to_name"] = assigned_to_name
    return _to_response(result)


@router.patch("/{newcomer_id}/status", response_model=NewcomerResponse)
def update_newcomer_status(
    newcomer_id: str,
    body: NewcomerStatusUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    allowed = {"visiting", "registered", "left"}

    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 상태입니다. 허용: {', '.join(allowed)}")

    with get_cursor() as cur:
        cur.execute(
            """UPDATE shalenu_newcomers SET status = %s, updated_at = NOW()
               WHERE id = %s AND church_id = %s
               RETURNING id, member_id, name, phone, email, gender, birth_date,
                         address, visit_date, visit_route, assigned_to, status,
                         note, created_at""",
            (body.status, newcomer_id, church_id),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="새가족을 찾을 수 없습니다")

        # registered 상태 변경 시 교인 자동 등록
        if body.status == "registered" and not row.get("member_id"):
            cur.execute(
                """INSERT INTO shalenu_members (church_id, name, phone, email, gender, birth_date, address, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')
                   RETURNING id""",
                (church_id, row["name"], row.get("phone"), row.get("email"),
                 row.get("gender"), row.get("birth_date"), row.get("address")),
            )
            new_member = cur.fetchone()
            cur.execute(
                "UPDATE shalenu_newcomers SET member_id = %s WHERE id = %s",
                (new_member["id"], newcomer_id),
            )
            row = dict(row)
            row["member_id"] = new_member["id"]

        assigned_to_name = None
        if row.get("assigned_to"):
            cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (row["assigned_to"],))
            am = cur.fetchone()
            if am:
                assigned_to_name = am["name"]

    result = dict(row)
    result["assigned_to_name"] = assigned_to_name
    return _to_response(result)
