from fastapi import APIRouter, Depends, HTTPException, Query, status

from db import get_cursor
from dependencies import get_current_user
from schemas.pledges import PledgeCreate, PledgeUpdate, PledgePayRequest, PledgeResponse

router = APIRouter(prefix="/api/v1/pledges", tags=["작정헌금 관리"])


def _to_response(row: dict) -> PledgeResponse:
    return PledgeResponse(
        id=str(row["id"]),
        member_id=str(row["member_id"]),
        member_name=row.get("member_name"),
        pledge_year=row["pledge_year"],
        offering_type=row["offering_type"],
        offering_type_label=row.get("offering_type_label"),
        pledged_amount=row["pledged_amount"],
        paid_amount=row["paid_amount"],
        status=row["status"],
        created_at=str(row["created_at"]),
    )


COLS = """p.id, p.member_id, p.pledge_year, p.offering_type,
          p.pledged_amount, p.paid_amount, p.status, p.created_at,
          m.name AS member_name,
          lc.label AS offering_type_label"""


@router.get("", response_model=list[PledgeResponse])
def list_pledges(
    year: int = Query(None, description="작정 연도"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    conditions = ["p.church_id = %s"]
    params: list = [church_id]

    if year:
        conditions.append("p.pledge_year = %s")
        params.append(year)

    where = " AND ".join(conditions)

    with get_cursor() as cur:
        cur.execute(
            f"""SELECT {COLS}
                FROM shalenu_offering_pledges p
                JOIN shalenu_members m ON p.member_id = m.id
                LEFT JOIN shalenu_lookup_codes lc
                  ON lc.church_id = p.church_id AND lc.category = 'offering_type'
                     AND lc.code = p.offering_type
                WHERE {where}
                ORDER BY m.name, p.offering_type""",
            params,
        )
        rows = cur.fetchall()

    return [_to_response(r) for r in rows]


@router.post("", response_model=PledgeResponse, status_code=status.HTTP_201_CREATED)
def create_pledge(body: PledgeCreate, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO shalenu_offering_pledges
               (church_id, member_id, pledge_year, offering_type, pledged_amount)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, member_id, pledge_year, offering_type,
                         pledged_amount, paid_amount, status, created_at""",
            (church_id, body.member_id, body.pledge_year, body.offering_type, body.pledged_amount),
        )
        row = cur.fetchone()

        cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (body.member_id,))
        member = cur.fetchone()

        cur.execute(
            "SELECT label FROM shalenu_lookup_codes WHERE church_id = %s AND category = 'offering_type' AND code = %s",
            (church_id, body.offering_type),
        )
        lc = cur.fetchone()

    result = dict(row)
    result["member_name"] = member["name"] if member else None
    result["offering_type_label"] = lc["label"] if lc else None
    return _to_response(result)


@router.put("/{pledge_id}", response_model=PledgeResponse)
def update_pledge(
    pledge_id: str,
    body: PledgeUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [pledge_id, church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_offering_pledges SET {set_clause}
                WHERE id = %s AND church_id = %s
                RETURNING id, member_id, pledge_year, offering_type,
                          pledged_amount, paid_amount, status, created_at""",
            values,
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="작정헌금을 찾을 수 없습니다")

        cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (row["member_id"],))
        member = cur.fetchone()

        cur.execute(
            "SELECT label FROM shalenu_lookup_codes WHERE church_id = %s AND category = 'offering_type' AND code = %s",
            (church_id, row["offering_type"]),
        )
        lc = cur.fetchone()

    result = dict(row)
    result["member_name"] = member["name"] if member else None
    result["offering_type_label"] = lc["label"] if lc else None
    return _to_response(result)


@router.patch("/{pledge_id}/pay", response_model=PledgeResponse)
def pay_pledge(
    pledge_id: str,
    body: PledgePayRequest,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="납입 금액은 0보다 커야 합니다")

    with get_cursor() as cur:
        cur.execute(
            """UPDATE shalenu_offering_pledges
               SET paid_amount = paid_amount + %s
               WHERE id = %s AND church_id = %s
               RETURNING id, member_id, pledge_year, offering_type,
                         pledged_amount, paid_amount, status, created_at""",
            (body.amount, pledge_id, church_id),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="작정헌금을 찾을 수 없습니다")

        # 납입 완료 시 자동 상태 변경
        if row["paid_amount"] >= row["pledged_amount"]:
            cur.execute(
                "UPDATE shalenu_offering_pledges SET status = 'completed' WHERE id = %s",
                (pledge_id,),
            )
            row = dict(row)
            row["status"] = "completed"

        cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (row["member_id"],))
        member = cur.fetchone()

        cur.execute(
            "SELECT label FROM shalenu_lookup_codes WHERE church_id = %s AND category = 'offering_type' AND code = %s",
            (church_id, row["offering_type"]),
        )
        lc = cur.fetchone()

    result = dict(row)
    result["member_name"] = member["name"] if member else None
    result["offering_type_label"] = lc["label"] if lc else None
    return _to_response(result)
