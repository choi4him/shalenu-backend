import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import Response

from db import get_cursor
from dependencies import get_current_user

router = APIRouter(prefix="/api/v1/backup", tags=["데이터 백업/복구"])

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
# 내보내기
# ────────────────────────────────────────────────
@router.get("/export")
def export_backup(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]
    data: dict[str, list] = {}

    with get_cursor() as cur:
        # 교회명
        cur.execute("SELECT name FROM shalenu_churches WHERE id = %s", (church_id,))
        row = cur.fetchone()
        church_name = row["name"] if row else ""

        # 직접 테이블
        for table in DIRECT_TABLES:
            try:
                cur.execute(f"SELECT * FROM {table} WHERE church_id = %s", (church_id,))
                data[table] = _rows_to_list(cur.fetchall())
            except Exception:
                data[table] = []

        # 자식 테이블
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

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"jsheepfold-backup-{date_str}.json"
    content = json.dumps(payload, default=_serialize, ensure_ascii=False, indent=2)

    return Response(
        content=content,
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

    # JSON 파싱
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
        # 전체 교체 모드
        if replace:
            # FK 순서를 고려해 자식 → 부모 순으로 삭제
            for entry in reversed(CHILD_TABLES):
                try:
                    # 자식 테이블은 church_id가 없으므로 부모 기준 삭제
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

        # 데이터 삽입
        for table in all_tables:
            rows = backup_data.get(table, [])
            for row in rows:
                # church_id 강제 설정 (직접 테이블만)
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
