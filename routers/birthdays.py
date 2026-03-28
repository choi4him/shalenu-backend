from fastapi import APIRouter, Depends, HTTPException, Query

from db import get_cursor
from dependencies import get_current_user
from schemas.birthdays import BirthdayMember, BirthdaySettingsUpdate, BirthdaySettingsResponse

router = APIRouter(prefix="/api/v1/birthdays", tags=["생일 알림"])


@router.get("/upcoming", response_model=list[BirthdayMember])
def list_upcoming_birthdays(
    days: int = Query(30, ge=1, le=90, description="며칠 이내 생일"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # 올해/내년 생일까지 고려하여 며칠 이내 생일자 조회
        cur.execute(
            """WITH upcoming AS (
                 SELECT id, name, birth_date, phone, email,
                   CASE
                     WHEN TO_CHAR(birth_date, 'MM-DD') >= TO_CHAR(CURRENT_DATE, 'MM-DD')
                     THEN MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::int,
                                    EXTRACT(MONTH FROM birth_date)::int,
                                    EXTRACT(DAY FROM birth_date)::int)
                     ELSE MAKE_DATE(EXTRACT(YEAR FROM CURRENT_DATE)::int + 1,
                                    EXTRACT(MONTH FROM birth_date)::int,
                                    EXTRACT(DAY FROM birth_date)::int)
                   END AS next_birthday
                 FROM shalenu_members
                 WHERE church_id = %s AND status = 'active' AND birth_date IS NOT NULL
               )
               SELECT id, name, birth_date, phone, email,
                      (next_birthday - CURRENT_DATE) AS days_until
               FROM upcoming
               WHERE (next_birthday - CURRENT_DATE) BETWEEN 0 AND %s
               ORDER BY days_until, name""",
            (church_id, days),
        )
        rows = cur.fetchall()

    return [
        BirthdayMember(
            id=str(r["id"]),
            name=r["name"],
            birth_date=r["birth_date"],
            phone=r.get("phone"),
            email=r.get("email"),
            days_until=r["days_until"],
        )
        for r in rows
    ]


@router.get("/settings", response_model=BirthdaySettingsResponse)
def get_birthday_settings(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            "SELECT id, alert_days_before, is_active, notify_via FROM shalenu_birthday_alerts WHERE church_id = %s",
            (church_id,),
        )
        row = cur.fetchone()

    if not row:
        return BirthdaySettingsResponse()

    return BirthdaySettingsResponse(
        id=str(row["id"]),
        alert_days_before=row["alert_days_before"],
        is_active=row["is_active"],
        notify_via=row["notify_via"],
    )


@router.put("/settings", response_model=BirthdaySettingsResponse)
def update_birthday_settings(
    body: BirthdaySettingsUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    if "notify_via" in updates and updates["notify_via"] not in {"sms", "email", "both"}:
        raise HTTPException(status_code=400, detail="유효하지 않은 알림 방식입니다. 허용: sms, email, both")

    with get_cursor() as cur:
        # UPSERT: 없으면 생성, 있으면 업데이트
        cur.execute(
            "SELECT id FROM shalenu_birthday_alerts WHERE church_id = %s",
            (church_id,),
        )
        existing = cur.fetchone()

        if existing:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [church_id]
            cur.execute(
                f"""UPDATE shalenu_birthday_alerts SET {set_clause}
                    WHERE church_id = %s
                    RETURNING id, alert_days_before, is_active, notify_via""",
                values,
            )
        else:
            cols = ["church_id"] + list(updates.keys())
            placeholders = ", ".join(["%s"] * len(cols))
            col_names = ", ".join(cols)
            values = [church_id] + list(updates.values())
            cur.execute(
                f"""INSERT INTO shalenu_birthday_alerts ({col_names})
                    VALUES ({placeholders})
                    RETURNING id, alert_days_before, is_active, notify_via""",
                values,
            )

        row = cur.fetchone()

    return BirthdaySettingsResponse(
        id=str(row["id"]),
        alert_days_before=row["alert_days_before"],
        is_active=row["is_active"],
        notify_via=row["notify_via"],
    )
