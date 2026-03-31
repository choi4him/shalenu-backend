from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status

from db import get_cursor
from dependencies import get_current_user
from schemas.offerings import (
    OfferingCreate,
    OfferingResponse,
    OfferingItemResponse,
    OfferingStatsResponse,
    OfferingTypeSummary,
    MonthlyOfferingItem,
    MemberOfferingStat,
)

router = APIRouter(prefix="/api/v1/offerings", tags=["헌금 관리"])


@router.get("/stats", response_model=OfferingStatsResponse)
def offering_stats(
    year: int = Query(None, description="조회 연도 (기본값: 현재 연도)"),
    current_user: dict = Depends(get_current_user),
):
    if year is None:
        year = datetime.now().year
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # 종류별 합계
        cur.execute(
            """SELECT o.offering_type AS type,
                      COALESCE(lc.label, o.offering_type) AS type_label,
                      COALESCE(SUM(o.total_amount), 0)::bigint AS total
               FROM shalenu_offerings o
               LEFT JOIN shalenu_lookup_codes lc
                 ON lc.church_id = o.church_id AND lc.category = 'offering_type' AND lc.code = o.offering_type
               WHERE o.church_id = %s
                 AND EXTRACT(YEAR FROM o.offering_date) = %s
               GROUP BY o.offering_type, lc.label, lc.sort_order
               ORDER BY lc.sort_order NULLS LAST""",
            (church_id, year),
        )
        type_rows = cur.fetchall()

        # 월별 + 종류별 합계
        cur.execute(
            """SELECT EXTRACT(MONTH FROM o.offering_date)::int AS month,
                      o.offering_type AS type,
                      COALESCE(SUM(o.total_amount), 0)::bigint AS amount
               FROM shalenu_offerings o
               WHERE o.church_id = %s
                 AND EXTRACT(YEAR FROM o.offering_date) = %s
               GROUP BY month, o.offering_type
               ORDER BY month, o.offering_type""",
            (church_id, year),
        )
        monthly_rows = cur.fetchall()

    by_type = [
        OfferingTypeSummary(type=r["type"], type_label=r["type_label"], total=r["total"])
        for r in type_rows
    ]
    monthly = [
        MonthlyOfferingItem(month=r["month"], type=r["type"], amount=r["amount"])
        for r in monthly_rows
    ]
    grand_total = sum(t.total for t in by_type)

    return OfferingStatsResponse(year=year, grand_total=grand_total, by_type=by_type, monthly=monthly)


@router.get("/stats/by-member", response_model=list[MemberOfferingStat])
def offering_stats_by_member(
    year: int = Query(None, description="조회 연도 (기본값: 현재 연도)"),
    current_user: dict = Depends(get_current_user),
):
    if year is None:
        year = datetime.now().year
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # member별 + offering_type별 집계
        cur.execute(
            """SELECT i.member_id,
                      COALESCE(m.name, i.giver_name, '미등록') AS member_name,
                      o.offering_type,
                      COALESCE(lc.label, o.offering_type) AS offering_type_name,
                      COALESCE(SUM(i.amount), 0)::bigint AS total
               FROM shalenu_offering_items i
               JOIN shalenu_offerings o ON o.id = i.offering_id
               LEFT JOIN shalenu_members m ON i.member_id = m.id
               LEFT JOIN shalenu_lookup_codes lc
                 ON lc.church_id = o.church_id AND lc.category = 'offering_type' AND lc.code = o.offering_type
               WHERE o.church_id = %s AND EXTRACT(YEAR FROM o.offering_date) = %s
               GROUP BY i.member_id, m.name, i.giver_name, o.offering_type, lc.label, lc.sort_order
               ORDER BY m.name NULLS LAST, lc.sort_order NULLS LAST""",
            (church_id, year),
        )
        rows = cur.fetchall()

    # member별로 그룹핑 — by_type은 {type_label: amount} dict
    member_map: dict[tuple, dict] = {}
    for r in rows:
        key = (str(r["member_id"]) if r["member_id"] else None, r["member_name"])
        if key not in member_map:
            member_map[key] = {"member_id": key[0], "member_name": key[1], "total": 0, "by_type": {}}
        member_map[key]["total"] += r["total"]
        type_label = r["offering_type_name"] or r["offering_type"]
        member_map[key]["by_type"][type_label] = (
            member_map[key]["by_type"].get(type_label, 0) + r["total"]
        )

    return [
        MemberOfferingStat(**v)
        for v in sorted(member_map.values(), key=lambda x: x["total"], reverse=True)
    ]


@router.get("")
def list_offerings(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    member_id: str = Query(None, description="교인별 헌금 이력 조회"),
    offering_type_code: str = Query(None, description="헌금 종류 필터"),
    date_from: str = Query(None, description="시작일 (YYYY-MM-DD)"),
    date_to: str = Query(None, description="종료일 (YYYY-MM-DD)"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    offset = (page - 1) * size

    with get_cursor() as cur:
        # 동적 WHERE 절 구성
        where_clauses = ["o.church_id = %s"]
        params: list = [church_id]

        if member_id:
            where_clauses.append(
                "o.id IN (SELECT offering_id FROM shalenu_offering_items WHERE member_id = %s)"
            )
            params.append(member_id)
        if offering_type_code:
            where_clauses.append("o.offering_type = %s")
            params.append(offering_type_code)
        if date_from:
            where_clauses.append("o.offering_date >= %s")
            params.append(date_from)
        if date_to:
            where_clauses.append("o.offering_date <= %s")
            params.append(date_to)

        where_sql = " AND ".join(where_clauses)

        # 총 개수
        cur.execute(f"SELECT COUNT(*) AS cnt FROM shalenu_offerings o WHERE {where_sql}", params)
        total = cur.fetchone()["cnt"]

        # 목록 (lookup JOIN으로 이름 포함)
        cur.execute(
            f"""SELECT o.id, o.offering_date, o.offering_type, o.worship_type,
                       o.total_amount, o.status, o.created_by, o.created_at,
                       ot.label AS offering_type_name,
                       wt.label AS worship_type_name,
                       (SELECT COUNT(*) FROM shalenu_offering_items WHERE offering_id = o.id) AS item_count
                FROM shalenu_offerings o
                LEFT JOIN shalenu_lookup_codes ot
                  ON ot.church_id = o.church_id AND ot.category = 'offering_type' AND ot.code = o.offering_type
                LEFT JOIN shalenu_lookup_codes wt
                  ON wt.church_id = o.church_id AND wt.category = 'worship_type' AND wt.code = o.worship_type
                WHERE {where_sql}
                ORDER BY o.offering_date DESC, o.created_at DESC
                LIMIT %s OFFSET %s""",
            params + [size, offset],
        )
        rows = cur.fetchall()

    pages = max(1, (total + size - 1) // size)
    items = [_to_offering_response(r) for r in rows]
    return {"items": items, "total": total, "page": page, "pages": pages, "size": size}


@router.post("", response_model=OfferingResponse, status_code=status.HTTP_201_CREATED)
def create_offering(
    body: OfferingCreate, current_user: dict = Depends(get_current_user)
):
    church_id = current_user["church_id"]
    user_id = current_user["user_id"]
    total_amount = sum(item.amount for item in body.items)

    with get_cursor() as cur:
        # 헌금 헤더 생성
        cur.execute(
            """INSERT INTO shalenu_offerings
               (church_id, offering_date, offering_type, worship_type, total_amount, status, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, offering_date, offering_type, worship_type,
                         total_amount, status, created_by, created_at""",
            (church_id, body.offering_date, body.offering_type_code, body.worship_type_code,
             total_amount, body.status, user_id),
        )
        offering_row = cur.fetchone()
        offering_id = str(offering_row["id"])

        # lookup 이름 조회
        cur.execute(
            "SELECT label FROM shalenu_lookup_codes WHERE church_id = %s AND category = 'offering_type' AND code = %s",
            (church_id, body.offering_type_code),
        )
        ot_row = cur.fetchone()
        offering_row["offering_type_name"] = ot_row["label"] if ot_row else None

        cur.execute(
            "SELECT label FROM shalenu_lookup_codes WHERE church_id = %s AND category = 'worship_type' AND code = %s",
            (church_id, body.worship_type_code),
        )
        wt_row = cur.fetchone()
        offering_row["worship_type_name"] = wt_row["label"] if wt_row else None

        # 헌금 항목(items) 생성 — member_id가 있으면 같은 교회 소속인지 검증
        item_rows = []
        for item in body.items:
            if item.member_id:
                cur.execute(
                    "SELECT id FROM shalenu_members WHERE id = %s AND church_id = %s AND status = 'active'",
                    (item.member_id, church_id),
                )
                if not cur.fetchone():
                    raise HTTPException(status_code=400, detail=f"존재하지 않는 교인입니다: {item.member_id}")

            # member_name은 giver_name 컬럼에 저장 (비회원 직접 입력 이름)
            giver_name = item.member_name if not item.member_id else None

            cur.execute(
                """WITH inserted AS (
                     INSERT INTO shalenu_offering_items
                     (offering_id, member_id, giver_name, amount, payment_method, note)
                     VALUES (%s, %s, %s, %s, %s, %s)
                     RETURNING id, offering_id, member_id, giver_name, amount, payment_method, note
                   )
                   SELECT ins.id, ins.offering_id, ins.member_id,
                          COALESCE(m.name, ins.giver_name) AS member_name,
                          ins.amount, ins.payment_method, ins.note AS notes
                   FROM inserted ins
                   LEFT JOIN shalenu_members m ON ins.member_id = m.id""",
                (offering_id, item.member_id, giver_name, item.amount, item.payment_method, item.notes),
            )
            item_rows.append(cur.fetchone())

    resp = _to_offering_response(offering_row)
    resp.items = [_to_item_response(r) for r in item_rows]
    return resp


@router.get("/{offering_id}", response_model=OfferingResponse)
def get_offering(offering_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT o.id, o.offering_date, o.offering_type, o.worship_type,
                      o.total_amount, o.status, o.created_by, o.created_at,
                      ot.label AS offering_type_name,
                      wt.label AS worship_type_name
               FROM shalenu_offerings o
               LEFT JOIN shalenu_lookup_codes ot
                 ON ot.church_id = o.church_id AND ot.category = 'offering_type' AND ot.code = o.offering_type
               LEFT JOIN shalenu_lookup_codes wt
                 ON wt.church_id = o.church_id AND wt.category = 'worship_type' AND wt.code = o.worship_type
               WHERE o.id = %s AND o.church_id = %s""",
            (offering_id, church_id),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="헌금 내역을 찾을 수 없습니다")

        cur.execute(
            """SELECT i.id, i.offering_id, i.member_id,
                      COALESCE(m.name, i.giver_name) AS member_name,
                      i.amount, i.payment_method, i.note AS notes
               FROM shalenu_offering_items i
               LEFT JOIN shalenu_members m ON i.member_id = m.id
               WHERE i.offering_id = %s
               ORDER BY i.id""",
            (offering_id,),
        )
        item_rows = cur.fetchall()

    resp = _to_offering_response(row)
    resp.items = [_to_item_response(r) for r in item_rows]
    return resp


@router.delete("/{offering_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offering(offering_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # 항목 먼저 삭제
        cur.execute(
            "DELETE FROM shalenu_offering_items WHERE offering_id = %s", (offering_id,)
        )
        cur.execute(
            "DELETE FROM shalenu_offerings WHERE id = %s AND church_id = %s RETURNING id",
            (offering_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="헌금 내역을 찾을 수 없습니다")


def _to_offering_response(row: dict) -> OfferingResponse:
    return OfferingResponse(
        id=str(row["id"]),
        offering_date=row["offering_date"],
        offering_type_code=row["offering_type"],
        offering_type_name=row.get("offering_type_name"),
        worship_type_code=row["worship_type"],
        worship_type_name=row.get("worship_type_name"),
        total_amount=row["total_amount"],
        status=row["status"],
        created_by=str(row["created_by"]) if row.get("created_by") else None,
        created_at=str(row["created_at"]),
        item_count=row.get("item_count"),
    )


def _to_item_response(row: dict) -> OfferingItemResponse:
    return OfferingItemResponse(
        id=str(row["id"]),
        offering_id=str(row["offering_id"]),
        member_id=str(row["member_id"]) if row.get("member_id") else None,
        member_name=row.get("member_name"),
        amount=row["amount"],
        payment_method=row.get("payment_method"),
        notes=row.get("notes"),
    )
