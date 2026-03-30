import calendar
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
import resend

from db import get_cursor
from dependencies import get_current_user

router = APIRouter(prefix="/api/v1/backup", tags=["데이터 백업/복구"])

resend.api_key = os.getenv("RESEND_API_KEY", "")

# 직접 church_id 컬럼을 가진 테이블
DIRECT_TABLES = [
    "shalenu_members",
    "shalenu_offerings",
    "shalenu_transactions",
    "shalenu_finance_accounts",
    "shalenu_budgets",
    "shalenu_small_groups",
    "shalenu_attendance_logs",
    "shalenu_newcomers",
    "shalenu_offering_pledges",
    "shalenu_pastoral_notes",
    "shalenu_lookup_codes",
]

# 부모 테이블을 통해 church_id를 찾는 자식 테이블
CHILD_TABLES = [
    {
        "table": "shalenu_offering_items",
        "query": """
            SELECT oi.* FROM shalenu_offering_items oi
            JOIN shalenu_offerings o ON oi.offering_id = o.id
            WHERE o.church_id = %s
        """,
    },
    {
        "table": "shalenu_budget_items",
        "query": """
            SELECT bi.* FROM shalenu_budget_items bi
            JOIN shalenu_budgets b ON bi.budget_id = b.id
            WHERE b.church_id = %s
        """,
    },
    {
        "table": "shalenu_small_group_members",
        "query": """
            SELECT sgm.* FROM shalenu_small_group_members sgm
            JOIN shalenu_small_groups sg ON sgm.small_group_id = sg.id
            WHERE sg.church_id = %s
        """,
    },
]


def _serialize(obj):
    """datetime/date/UUID 등 JSON 비직렬화 타입 처리."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def _rows_to_list(rows) -> list[dict]:
    return [dict(row) for row in rows] if rows else []


# ────────────────────────────────────────────────
# 공유 헬퍼 (scheduler.py에서도 사용)
# ────────────────────────────────────────────────
def _next_backup_at(frequency: str, from_dt: datetime) -> datetime:
    """frequency에 따른 다음 백업 일시 계산."""
    if frequency == "weekly":
        return from_dt + timedelta(weeks=1)
    # monthly: 같은 날짜 다음 달 (말일 초과 시 말일로)
    month = from_dt.month + 1
    year = from_dt.year
    if month > 12:
        month, year = 1, year + 1
    day = min(from_dt.day, calendar.monthrange(year, month)[1])
    return from_dt.replace(year=year, month=month, day=day)


def _generate_backup(church_id: str) -> tuple[str, str]:
    """교회 데이터를 JSON 문자열로 직렬화. (json_str, church_name) 반환."""
    data: dict[str, list] = {}
    with get_cursor() as cur:
        cur.execute("SELECT name FROM shalenu_churches WHERE id = %s", (church_id,))
        row = cur.fetchone()
        church_name = row["name"] if row else ""

        for table in DIRECT_TABLES:
            try:
                cur.execute(f"SELECT * FROM {table} WHERE church_id = %s", (church_id,))
                data[table] = _rows_to_list(cur.fetchall())
            except Exception:
                data[table] = []

        for entry in CHILD_TABLES:
            try:
                cur.execute(entry["query"], (church_id,))
                data[entry["table"]] = _rows_to_list(cur.fetchall())
            except Exception:
                data[entry["table"]] = []

    payload = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "church_name": church_name,
        "data": data,
    }
    return json.dumps(payload, default=_serialize, ensure_ascii=False, indent=2), church_name


def _send_backup_email(send_to: str, church_name: str, json_str: str, date_str: str) -> None:
    """Resend로 백업 JSON을 첨부하여 이메일 발송."""
    filename = f"jsheepfold-backup-{date_str}.json"
    resend.Emails.send({
        "from": "J-SheepFold <backup@jsheepfold.com>",
        "to": [send_to],
        "subject": f"[J-SheepFold] 자동 백업 — {church_name} {date_str}",
        "text": (
            f"안녕하세요,\n\n"
            f"{church_name}의 자동 백업 파일을 첨부합니다.\n"
            f"첨부 파일에서 백업 데이터를 확인하세요.\n\n"
            f"— J-SheepFold"
        ),
        "attachments": [
            {
                "filename": filename,
                "content": list(json_str.encode("utf-8")),
            }
        ],
    })


# ────────────────────────────────────────────────
# 내보내기
# ────────────────────────────────────────────────
@router.get("/export")
def export_backup(current_user: dict = Depends(get_current_user)):
    church_id = str(current_user["church_id"])
    json_str, _ = _generate_backup(church_id)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"jsheepfold-backup-{date_str}.json"

    return Response(
        content=json_str,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ────────────────────────────────────────────────
# 가져오기
# ────────────────────────────────────────────────
@router.post("/import")
async def import_backup(
    file: UploadFile = File(...),
    replace: bool = Query(False, description="True면 기존 데이터 전체 삭제 후 교체"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    try:
        raw = await file.read()
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="유효하지 않은 JSON 파일입니다.")

    if payload.get("version") != "1.0":
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 백업 버전입니다: {payload.get('version')}",
        )

    backup_data: dict = payload.get("data", {})
    all_tables = DIRECT_TABLES + [e["table"] for e in CHILD_TABLES]

    imported: dict[str, int] = {t: 0 for t in all_tables}
    skipped: dict[str, int] = {t: 0 for t in all_tables}
    errors: list[str] = []

    with get_cursor() as cur:
        if replace:
            for entry in reversed(CHILD_TABLES):
                try:
                    table = entry["table"]
                    if table == "shalenu_offering_items":
                        cur.execute(
                            "DELETE FROM shalenu_offering_items WHERE offering_id IN "
                            "(SELECT id FROM shalenu_offerings WHERE church_id = %s)",
                            (church_id,),
                        )
                    elif table == "shalenu_budget_items":
                        cur.execute(
                            "DELETE FROM shalenu_budget_items WHERE budget_id IN "
                            "(SELECT id FROM shalenu_budgets WHERE church_id = %s)",
                            (church_id,),
                        )
                    elif table == "shalenu_small_group_members":
                        cur.execute(
                            "DELETE FROM shalenu_small_group_members WHERE small_group_id IN "
                            "(SELECT id FROM shalenu_small_groups WHERE church_id = %s)",
                            (church_id,),
                        )
                except Exception as e:
                    errors.append(f"삭제 실패 {entry['table']}: {e}")

            for table in reversed(DIRECT_TABLES):
                try:
                    cur.execute(f"DELETE FROM {table} WHERE church_id = %s", (church_id,))
                except Exception as e:
                    errors.append(f"삭제 실패 {table}: {e}")

        for table in all_tables:
            rows = backup_data.get(table, [])
            for row in rows:
                if table in DIRECT_TABLES:
                    row["church_id"] = church_id

                try:
                    cols = list(row.keys())
                    if not cols:
                        continue
                    placeholders = ", ".join(["%s"] * len(cols))
                    col_names = ", ".join(f'"{c}"' for c in cols)
                    vals = [row[c] for c in cols]

                    cur.execute(
                        f'INSERT INTO {table} ({col_names}) VALUES ({placeholders}) '
                        f'ON CONFLICT (id) DO NOTHING',
                        vals,
                    )
                    if cur.rowcount > 0:
                        imported[table] += 1
                    else:
                        skipped[table] += 1
                except Exception as e:
                    skipped[table] += 1
                    if len(errors) < 20:
                        errors.append(f"{table}: {e}")

    return {"imported": imported, "skipped": skipped, "errors": errors}


# ────────────────────────────────────────────────
# 자동 백업 이메일 설정
# ────────────────────────────────────────────────
def _row_to_settings(row) -> dict:
    d = dict(row)
    for k in ("last_backup_at", "next_backup_at", "created_at"):
        if k in d and d[k] is not None:
            d[k] = d[k].isoformat()
    return d


@router.get("/settings")
def get_backup_settings(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]
    with get_cursor() as cur:
        cur.execute(
            "SELECT * FROM shalenu_backup_settings WHERE church_id = %s",
            (church_id,),
        )
        row = cur.fetchone()
    if not row:
        return {
            "is_enabled": False,
            "frequency": "monthly",
            "send_to_email": "",
            "last_backup_at": None,
            "next_backup_at": None,
        }
    return _row_to_settings(row)


class BackupSettingsIn(BaseModel):
    is_enabled: bool
    frequency: str   # "weekly" | "monthly"
    send_to_email: str


@router.put("/settings")
def update_backup_settings(
    body: BackupSettingsIn,
    current_user: dict = Depends(get_current_user),
):
    if body.frequency not in ("weekly", "monthly"):
        raise HTTPException(status_code=422, detail="frequency는 weekly 또는 monthly 이어야 합니다.")

    church_id = current_user["church_id"]
    now = datetime.now(timezone.utc)
    next_at = _next_backup_at(body.frequency, now)

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO shalenu_backup_settings
                (church_id, is_enabled, frequency, send_to_email, next_backup_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (church_id) DO UPDATE
              SET is_enabled     = EXCLUDED.is_enabled,
                  frequency      = EXCLUDED.frequency,
                  send_to_email  = EXCLUDED.send_to_email,
                  next_backup_at = EXCLUDED.next_backup_at
            RETURNING *
            """,
            (church_id, body.is_enabled, body.frequency, body.send_to_email, next_at),
        )
        row = cur.fetchone()
    return _row_to_settings(row)


# ────────────────────────────────────────────────
# 즉시 백업 이메일 발송
# ────────────────────────────────────────────────
@router.post("/send-now")
def send_backup_now(current_user: dict = Depends(get_current_user)):
    church_id = str(current_user["church_id"])

    with get_cursor() as cur:
        cur.execute(
            "SELECT send_to_email FROM shalenu_backup_settings WHERE church_id = %s",
            (church_id,),
        )
        row = cur.fetchone()

    if not row or not row.get("send_to_email"):
        raise HTTPException(
            status_code=400,
            detail="이메일 설정이 없습니다. 먼저 자동 백업 이메일을 설정하세요.",
        )

    send_to = row["send_to_email"]
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    json_str, church_name = _generate_backup(church_id)
    _send_backup_email(send_to, church_name, json_str, date_str)

    with get_cursor() as cur:
        cur.execute(
            "UPDATE shalenu_backup_settings SET last_backup_at = %s WHERE church_id = %s",
            (now, church_id),
        )

    return {"status": "sent", "to": send_to}
