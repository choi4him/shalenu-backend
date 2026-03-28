from fastapi import APIRouter, Depends, HTTPException, Query, status

from db import get_cursor
from dependencies import get_current_user
from schemas.facilities import (
    FacilityCreate, FacilityUpdate, FacilityResponse,
    BookingCreate, BookingStatusUpdate, BookingResponse,
)

router = APIRouter(prefix="/api/v1/facilities", tags=["시설 관리"])


# ── 시설 CRUD ──────────────────────────────────────────

@router.get("", response_model=list[FacilityResponse])
def list_facilities(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT id, name, capacity, description, is_active, created_at
               FROM shalenu_facilities
               WHERE church_id = %s
               ORDER BY name""",
            (church_id,),
        )
        rows = cur.fetchall()

    return [_to_facility(r) for r in rows]


@router.post("", response_model=FacilityResponse, status_code=status.HTTP_201_CREATED)
def create_facility(body: FacilityCreate, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO shalenu_facilities (church_id, name, capacity, description)
               VALUES (%s, %s, %s, %s)
               RETURNING id, name, capacity, description, is_active, created_at""",
            (church_id, body.name, body.capacity, body.description),
        )
        row = cur.fetchone()

    return _to_facility(row)


@router.put("/{facility_id}", response_model=FacilityResponse)
def update_facility(
    facility_id: str,
    body: FacilityUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [facility_id, church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_facilities SET {set_clause}
                WHERE id = %s AND church_id = %s
                RETURNING id, name, capacity, description, is_active, created_at""",
            values,
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")
    return _to_facility(row)


# ── 전체 예약 조회 (모든 시설) ─────────────────────────

@router.get("/bookings", response_model=list[BookingResponse])
def list_all_bookings(
    status_filter: str = Query(None, alias="status"),
    year: int = Query(None),
    month: int = Query(None),
    limit: int = Query(200),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    conditions = ["b.church_id = %s"]
    params: list = [church_id]

    if status_filter:
        conditions.append("b.status = %s")
        params.append(status_filter)
    if year:
        conditions.append("EXTRACT(YEAR FROM b.start_time) = %s")
        params.append(year)
    if month:
        conditions.append("EXTRACT(MONTH FROM b.start_time) = %s")
        params.append(month)

    where = " AND ".join(conditions)
    params.append(limit)

    with get_cursor() as cur:
        cur.execute(
            f"""SELECT b.id, b.facility_id, b.title, b.booked_by,
                       b.start_time, b.end_time, b.status, b.note, b.created_at,
                       f.name AS facility_name,
                       am.name AS booked_by_name
                FROM shalenu_facility_bookings b
                JOIN shalenu_facilities f ON b.facility_id = f.id
                JOIN shalenu_users u ON b.booked_by = u.id
                LEFT JOIN shalenu_members am ON u.member_id = am.id
                WHERE {where}
                ORDER BY b.start_time
                LIMIT %s""",
            params,
        )
        rows = cur.fetchall()

    return [_to_booking(r) for r in rows]


# ── 시설별 예약 ──────────────────────────────────────────

@router.get("/{facility_id}/bookings", response_model=list[BookingResponse])
def list_bookings(
    facility_id: str,
    status_filter: str = Query(None, alias="status", description="상태 필터"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    conditions = ["b.church_id = %s", "b.facility_id = %s"]
    params: list = [church_id, facility_id]

    if status_filter:
        conditions.append("b.status = %s")
        params.append(status_filter)

    where = " AND ".join(conditions)

    with get_cursor() as cur:
        cur.execute(
            f"""SELECT b.id, b.facility_id, b.title, b.booked_by,
                       b.start_time, b.end_time, b.status, b.note, b.created_at,
                       f.name AS facility_name,
                       am.name AS booked_by_name
                FROM shalenu_facility_bookings b
                JOIN shalenu_facilities f ON b.facility_id = f.id
                JOIN shalenu_users u ON b.booked_by = u.id
                LEFT JOIN shalenu_members am ON u.member_id = am.id
                WHERE {where}
                ORDER BY b.start_time""",
            params,
        )
        rows = cur.fetchall()

    return [_to_booking(r) for r in rows]


@router.post("/{facility_id}/bookings", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    facility_id: str,
    body: BookingCreate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    user_id = str(current_user["user_id"])

    if body.end_time <= body.start_time:
        raise HTTPException(status_code=400, detail="종료 시간은 시작 시간 이후여야 합니다")

    with get_cursor() as cur:
        # 시설 존재 확인
        cur.execute(
            "SELECT id FROM shalenu_facilities WHERE id = %s AND church_id = %s",
            (facility_id, church_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")

        # 시간 겹침 확인 (취소 제외)
        cur.execute(
            """SELECT id FROM shalenu_facility_bookings
               WHERE facility_id = %s AND status != 'cancelled'
                     AND start_time < %s AND end_time > %s""",
            (facility_id, body.end_time, body.start_time),
        )
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="해당 시간에 이미 예약이 있습니다")

        cur.execute(
            """INSERT INTO shalenu_facility_bookings
               (church_id, facility_id, title, booked_by, start_time, end_time, note)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, facility_id, title, booked_by, start_time, end_time,
                         status, note, created_at""",
            (church_id, facility_id, body.title, user_id, body.start_time, body.end_time, body.note),
        )
        row = cur.fetchone()

        cur.execute("SELECT name FROM shalenu_facilities WHERE id = %s", (facility_id,))
        facility = cur.fetchone()

        cur.execute(
            """SELECT am.name FROM shalenu_users u
               LEFT JOIN shalenu_members am ON u.member_id = am.id
               WHERE u.id = %s""",
            (user_id,),
        )
        booker = cur.fetchone()

    result = dict(row)
    result["facility_name"] = facility["name"] if facility else None
    result["booked_by_name"] = booker["name"] if booker else None
    return _to_booking(result)


@router.patch("/bookings/{booking_id}/status", response_model=BookingResponse)
def update_booking_status(
    booking_id: str,
    body: BookingStatusUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    allowed = {"approved", "cancelled"}

    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 상태입니다. 허용: {', '.join(allowed)}")

    with get_cursor() as cur:
        cur.execute(
            """UPDATE shalenu_facility_bookings SET status = %s
               WHERE id = %s AND church_id = %s
               RETURNING id, facility_id, title, booked_by, start_time, end_time,
                         status, note, created_at""",
            (body.status, booking_id, church_id),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다")

        cur.execute("SELECT name FROM shalenu_facilities WHERE id = %s", (row["facility_id"],))
        facility = cur.fetchone()

        cur.execute(
            """SELECT am.name FROM shalenu_users u
               LEFT JOIN shalenu_members am ON u.member_id = am.id
               WHERE u.id = %s""",
            (row["booked_by"],),
        )
        booker = cur.fetchone()

    result = dict(row)
    result["facility_name"] = facility["name"] if facility else None
    result["booked_by_name"] = booker["name"] if booker else None
    return _to_booking(result)


# ── 헬퍼 ──────────────────────────────────────────────

def _to_facility(row: dict) -> FacilityResponse:
    return FacilityResponse(
        id=str(row["id"]),
        name=row["name"],
        capacity=row.get("capacity"),
        description=row.get("description"),
        is_active=row.get("is_active", True),
        created_at=str(row["created_at"]),
    )


def _to_booking(row: dict) -> BookingResponse:
    return BookingResponse(
        id=str(row["id"]),
        facility_id=str(row["facility_id"]),
        facility_name=row.get("facility_name"),
        title=row["title"],
        booked_by=str(row["booked_by"]),
        booked_by_name=row.get("booked_by_name"),
        start_time=str(row["start_time"]),
        end_time=str(row["end_time"]),
        status=row["status"],
        note=row.get("note"),
        created_at=str(row["created_at"]),
    )
