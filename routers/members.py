from fastapi import APIRouter, Depends, HTTPException, Query, status

from db import get_cursor
from dependencies import get_current_user
from schemas.members import MemberCreate, MemberUpdate, MemberResponse

router = APIRouter(prefix="/api/v1/members", tags=["교인 관리"])


@router.get("")
def list_members(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="이름 검색"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    offset = (page - 1) * size

    with get_cursor() as cur:
        if search:
            cur.execute(
                """SELECT COUNT(*) AS cnt FROM shalenu_members
                   WHERE church_id = %s AND status = 'active' AND name ILIKE %s""",
                (church_id, f"%{search}%"),
            )
        else:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM shalenu_members WHERE church_id = %s AND status = 'active'",
                (church_id,),
            )
        total = cur.fetchone()["cnt"]

        if search:
            cur.execute(
                """SELECT id, name, gender, phone, email, address, birth_date,
                          join_date, baptism_date, status, created_at
                   FROM shalenu_members
                   WHERE church_id = %s AND status = 'active' AND name ILIKE %s
                   ORDER BY name
                   LIMIT %s OFFSET %s""",
                (church_id, f"%{search}%", size, offset),
            )
        else:
            cur.execute(
                """SELECT id, name, gender, phone, email, address, birth_date,
                          join_date, baptism_date, status, created_at
                   FROM shalenu_members
                   WHERE church_id = %s AND status = 'active'
                   ORDER BY name
                   LIMIT %s OFFSET %s""",
                (church_id, size, offset),
            )
        rows = cur.fetchall()

    items = [_to_response(r) for r in rows]
    return {"items": items, "total": total, "page": page, "size": size}


PLAN_MEMBER_LIMITS = {
    "free": 100,
    "growth": 500,
    "community": 2000,
    "enterprise": None,  # 무제한
}


@router.post("", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
def create_member(body: MemberCreate, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # 요금제별 교인 수 한도 확인
        cur.execute(
            "SELECT plan FROM shalenu_churches WHERE id = %s", (church_id,)
        )
        church = cur.fetchone()
        plan = church["plan"] if church else "free"
        limit = PLAN_MEMBER_LIMITS.get(plan)

        if limit is not None:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM shalenu_members WHERE church_id = %s AND status = 'active'",
                (church_id,),
            )
            current_count = cur.fetchone()["cnt"]
            if current_count >= limit:
                raise HTTPException(
                    status_code=403,
                    detail=f"현재 요금제({plan})의 교인 한도({limit}명)에 도달했습니다. 요금제를 업그레이드해주세요.",
                )

        cur.execute(
            """INSERT INTO shalenu_members
               (church_id, name, gender, phone, email, address, birth_date, join_date, baptism_date, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, name, gender, phone, email, address, birth_date,
                         join_date, baptism_date, status, created_at""",
            (
                church_id,
                body.name,
                body.gender,
                body.phone,
                body.email,
                body.address,
                body.birth_date,
                body.join_date,
                body.baptism_date,
                body.status,
            ),
        )
        row = cur.fetchone()

    return _to_response(row)


@router.get("/{member_id}", response_model=MemberResponse)
def get_member(member_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT id, name, gender, phone, email, address, birth_date,
                      join_date, baptism_date, status, created_at
               FROM shalenu_members WHERE id = %s AND church_id = %s""",
            (member_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="교인을 찾을 수 없습니다")
    return _to_response(row)


@router.put("/{member_id}", response_model=MemberResponse)
def update_member(
    member_id: str,
    body: MemberUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    allowed_columns = {"name", "gender", "phone", "email", "address", "birth_date", "join_date", "baptism_date", "status"}
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in allowed_columns}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [member_id, church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_members SET {set_clause}
                WHERE id = %s AND church_id = %s
                RETURNING id, name, gender, phone, email, address, birth_date,
                          join_date, baptism_date, status, created_at""",
            values,
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="교인을 찾을 수 없습니다")
    return _to_response(row)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(member_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            "UPDATE shalenu_members SET status = 'inactive' WHERE id = %s AND church_id = %s RETURNING id",
            (member_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="교인을 찾을 수 없습니다")


def _to_response(row: dict) -> MemberResponse:
    return MemberResponse(
        id=str(row["id"]),
        name=row["name"],
        gender=row.get("gender"),
        phone=row.get("phone"),
        email=row.get("email"),
        address=row.get("address"),
        birth_date=row.get("birth_date"),
        join_date=row.get("join_date"),
        baptism_date=row.get("baptism_date"),
        status=row["status"],
        created_at=str(row["created_at"]),
    )
