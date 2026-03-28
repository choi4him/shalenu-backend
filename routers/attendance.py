from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_cursor
from dependencies import get_current_user
from plan_check import require_feature
from schemas.attendance import AttendanceBatchCreate, AttendanceResponse, AttendanceStatsResponse

router = APIRouter(prefix="/api/v1/attendance", tags=["출석 관리"], dependencies=[Depends(require_feature("community"))])


@router.get("", response_model=list[AttendanceResponse])
def list_attendance(
    attendance_date: str = Query(None, description="출석일 (YYYY-MM-DD)"),
    service_id: str = Query(None, description="예배 ID"),
    member_id: str = Query(None, description="교인 ID"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    conditions = ["a.church_id = %s"]
    params: list = [church_id]

    if attendance_date:
        conditions.append("a.attendance_date = %s")
        params.append(attendance_date)
    if service_id:
        conditions.append("a.service_id = %s")
        params.append(service_id)
    if member_id:
        conditions.append("a.member_id = %s")
        params.append(member_id)

    where = " AND ".join(conditions)

    with get_cursor() as cur:
        cur.execute(
            f"""SELECT a.id, a.member_id, a.service_id, a.attendance_date, a.status, a.note,
                       m.name AS member_name,
                       ws.name AS service_name
                FROM shalenu_attendance_logs a
                JOIN shalenu_members m ON a.member_id = m.id
                LEFT JOIN shalenu_worship_services ws ON a.service_id = ws.id
                WHERE {where}
                ORDER BY m.name""",
            params,
        )
        rows = cur.fetchall()

    return [
        AttendanceResponse(
            id=str(r["id"]),
            member_id=str(r["member_id"]),
            member_name=r.get("member_name"),
            service_id=str(r["service_id"]) if r.get("service_id") else None,
            service_name=r.get("service_name"),
            attendance_date=r["attendance_date"],
            status=r["status"],
            note=r.get("note"),
        )
        for r in rows
    ]


@router.post("/batch", response_model=dict)
def batch_create_attendance(
    body: AttendanceBatchCreate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    created = 0
    updated = 0

    with get_cursor() as cur:
        for entry in body.entries:
            # UPSERT: 같은 날짜/예배/교인 조합이 있으면 업데이트
            cur.execute(
                """INSERT INTO shalenu_attendance_logs
                   (church_id, member_id, service_id, attendance_date, status, note)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (church_id, member_id, service_id, attendance_date)
                   DO UPDATE SET status = EXCLUDED.status, note = EXCLUDED.note
                   RETURNING (xmax = 0) AS is_insert""",
                (church_id, entry.member_id, body.service_id, body.attendance_date, entry.status, entry.note),
            )
            row = cur.fetchone()
            if row and row["is_insert"]:
                created += 1
            else:
                updated += 1

    return {"created": created, "updated": updated, "total": created + updated}


@router.get("/stats", response_model=AttendanceStatsResponse)
def get_attendance_stats(
    year: int = Query(..., description="통계 연도"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # 총 예배 횟수 (날짜+예배 조합)
        cur.execute(
            """SELECT COUNT(DISTINCT (attendance_date, service_id)) AS cnt
               FROM shalenu_attendance_logs
               WHERE church_id = %s AND EXTRACT(YEAR FROM attendance_date) = %s""",
            (church_id, year),
        )
        total_services = cur.fetchone()["cnt"]

        # 평균 출석 (present 기준)
        cur.execute(
            """SELECT COALESCE(AVG(cnt), 0) AS avg_att
               FROM (
                   SELECT attendance_date, service_id, COUNT(*) AS cnt
                   FROM shalenu_attendance_logs
                   WHERE church_id = %s AND EXTRACT(YEAR FROM attendance_date) = %s
                         AND status = 'present'
                   GROUP BY attendance_date, service_id
               ) sub""",
            (church_id, year),
        )
        avg_attendance = float(cur.fetchone()["avg_att"])

        # 예배별 통계
        cur.execute(
            """SELECT ws.name AS service_name, COUNT(*) AS total,
                      SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) AS present_count
               FROM shalenu_attendance_logs a
               LEFT JOIN shalenu_worship_services ws ON a.service_id = ws.id
               WHERE a.church_id = %s AND EXTRACT(YEAR FROM a.attendance_date) = %s
               GROUP BY ws.name
               ORDER BY ws.name""",
            (church_id, year),
        )
        by_service = [
            {"service_name": r["service_name"] or "미지정", "total": r["total"], "present": r["present_count"]}
            for r in cur.fetchall()
        ]

        # 월별 통계
        cur.execute(
            """SELECT EXTRACT(MONTH FROM attendance_date)::int AS month,
                      COUNT(*) AS total,
                      SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) AS present_count
               FROM shalenu_attendance_logs
               WHERE church_id = %s AND EXTRACT(YEAR FROM attendance_date) = %s
               GROUP BY month
               ORDER BY month""",
            (church_id, year),
        )
        monthly = [
            {"month": r["month"], "total": r["total"], "present": r["present_count"]}
            for r in cur.fetchall()
        ]

    return AttendanceStatsResponse(
        total_services=total_services,
        avg_attendance=round(avg_attendance, 1),
        by_service=by_service,
        monthly=monthly,
    )
