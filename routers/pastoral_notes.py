from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional

from db import get_cursor
from dependencies import get_current_user
from plan_check import require_feature
from schemas.pastoral_notes import PastoralNoteCreate, PastoralNoteUpdate, PastoralNoteResponse

router = APIRouter(prefix="/api/v1/pastoral-notes", tags=["목양 노트"], dependencies=[Depends(require_feature("pastoral"))])

ALLOWED_CATEGORIES = {"visit", "counsel", "prayer", "general"}


@router.get("", response_model=list[PastoralNoteResponse])
def list_pastoral_notes(
    member_id: Optional[str] = Query(None, description="교인 ID (없으면 전체 최근 노트)"),
    days: Optional[int] = Query(None, description="최근 N일 이내 노트"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="조회 건수 제한"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    user_id = str(current_user["user_id"])

    with get_cursor() as cur:
        where_clauses = [
            "pn.church_id = %s",
            "(pn.is_private = FALSE OR pn.author_id = %s)",
        ]
        params: list = [church_id, user_id]

        if member_id:
            where_clauses.append("pn.member_id = %s")
            params.append(member_id)
        if days:
            where_clauses.append("pn.created_at >= NOW() - INTERVAL '%s days'")
            params.append(days)

        where_sql = " AND ".join(where_clauses)
        limit_sql = f"LIMIT {int(limit)}" if limit else ""

        cur.execute(
            f"""SELECT pn.id, pn.member_id, pn.author_id, pn.category,
                      pn.content, pn.is_private, pn.visited_at,
                      pn.created_at, pn.updated_at,
                      m.name AS member_name,
                      u.email AS author_email,
                      am.name AS author_name
               FROM shalenu_pastoral_notes pn
               JOIN shalenu_members m ON pn.member_id = m.id
               JOIN shalenu_users u ON pn.author_id = u.id
               LEFT JOIN shalenu_members am ON u.member_id = am.id
               WHERE {where_sql}
               ORDER BY pn.created_at DESC
               {limit_sql}""",
            params,
        )
        rows = cur.fetchall()

    return [_to_response(r) for r in rows]


@router.post("", response_model=PastoralNoteResponse, status_code=status.HTTP_201_CREATED)
def create_pastoral_note(body: PastoralNoteCreate, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]
    user_id = str(current_user["user_id"])

    if body.category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 카테고리입니다. 허용: {', '.join(ALLOWED_CATEGORIES)}")

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO shalenu_pastoral_notes
               (church_id, member_id, author_id, category, content, is_private, visited_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id, member_id, author_id, category, content, is_private,
                         visited_at, created_at, updated_at""",
            (church_id, body.member_id, user_id, body.category, body.content,
             body.is_private, body.visited_at),
        )
        row = cur.fetchone()

        cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (body.member_id,))
        member = cur.fetchone()

        cur.execute(
            """SELECT am.name FROM shalenu_users u
               LEFT JOIN shalenu_members am ON u.member_id = am.id
               WHERE u.id = %s""",
            (user_id,),
        )
        author = cur.fetchone()

    result = dict(row)
    result["member_name"] = member["name"] if member else None
    result["author_name"] = author["name"] if author else None
    return _to_response(result)


@router.put("/{note_id}", response_model=PastoralNoteResponse)
def update_pastoral_note(
    note_id: str,
    body: PastoralNoteUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    user_id = str(current_user["user_id"])
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    if "category" in updates and updates["category"] not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 카테고리입니다. 허용: {', '.join(ALLOWED_CATEGORIES)}")

    updates["updated_at"] = "NOW()"
    set_parts = []
    values = []
    for k, v in updates.items():
        if v == "NOW()":
            set_parts.append(f"{k} = NOW()")
        else:
            set_parts.append(f"{k} = %s")
            values.append(v)
    set_clause = ", ".join(set_parts)
    values += [note_id, church_id, user_id]

    with get_cursor() as cur:
        # 작성자 본인만 수정 가능
        cur.execute(
            f"""UPDATE shalenu_pastoral_notes SET {set_clause}
                WHERE id = %s AND church_id = %s AND author_id = %s
                RETURNING id, member_id, author_id, category, content, is_private,
                          visited_at, created_at, updated_at""",
            values,
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="목양 노트를 찾을 수 없거나 수정 권한이 없습니다")

        cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (row["member_id"],))
        member = cur.fetchone()

        cur.execute(
            """SELECT am.name FROM shalenu_users u
               LEFT JOIN shalenu_members am ON u.member_id = am.id
               WHERE u.id = %s""",
            (row["author_id"],),
        )
        author = cur.fetchone()

    result = dict(row)
    result["member_name"] = member["name"] if member else None
    result["author_name"] = author["name"] if author else None
    return _to_response(result)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pastoral_note(note_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]
    user_id = str(current_user["user_id"])

    with get_cursor() as cur:
        # 작성자 본인만 삭제 가능
        cur.execute(
            "DELETE FROM shalenu_pastoral_notes WHERE id = %s AND church_id = %s AND author_id = %s RETURNING id",
            (note_id, church_id, user_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="목양 노트를 찾을 수 없거나 삭제 권한이 없습니다")


def _to_response(row: dict) -> PastoralNoteResponse:
    return PastoralNoteResponse(
        id=str(row["id"]),
        member_id=str(row["member_id"]),
        member_name=row.get("member_name"),
        author_id=str(row["author_id"]),
        author_name=row.get("author_name"),
        category=row["category"],
        content=row["content"],
        is_private=row["is_private"],
        visited_at=row.get("visited_at"),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
