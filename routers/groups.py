from fastapi import APIRouter, Depends, HTTPException, status

from db import get_cursor
from dependencies import get_current_user
from plan_check import require_feature
from schemas.groups import (
    GroupCreate, GroupUpdate, GroupResponse,
    GroupMemberAdd, GroupMemberResponse,
)

router = APIRouter(prefix="/api/v1/groups", tags=["구역/소그룹 관리"], dependencies=[Depends(require_feature("community"))])


def _to_group(row: dict) -> GroupResponse:
    return GroupResponse(
        id=str(row["id"]),
        name=row["name"],
        group_type=row.get("group_type"),
        leader_id=str(row["leader_id"]) if row.get("leader_id") else None,
        leader_name=row.get("leader_name"),
        description=row.get("description"),
        is_active=row.get("is_active", True),
        member_count=row.get("member_count", 0),
        created_at=str(row["created_at"]),
    )


@router.get("", response_model=list[GroupResponse])
def list_groups(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT g.id, g.name, g.group_type, g.leader_id, g.description,
                      g.is_active, g.created_at,
                      m.name AS leader_name,
                      (SELECT COUNT(*) FROM shalenu_small_group_members sgm
                       WHERE sgm.small_group_id = g.id AND sgm.is_active = TRUE) AS member_count
               FROM shalenu_small_groups g
               LEFT JOIN shalenu_members m ON g.leader_id = m.id
               WHERE g.church_id = %s
               ORDER BY g.name""",
            (church_id,),
        )
        rows = cur.fetchall()

    return [_to_group(r) for r in rows]


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(body: GroupCreate, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO shalenu_small_groups (church_id, name, group_type, leader_id, description)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, name, group_type, leader_id, description, is_active, created_at""",
            (church_id, body.name, body.group_type, body.leader_id, body.description),
        )
        row = cur.fetchone()

        leader_name = None
        if row.get("leader_id"):
            cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (row["leader_id"],))
            lm = cur.fetchone()
            if lm:
                leader_name = lm["name"]

    return GroupResponse(
        id=str(row["id"]),
        name=row["name"],
        group_type=row.get("group_type"),
        leader_id=str(row["leader_id"]) if row.get("leader_id") else None,
        leader_name=leader_name,
        description=row.get("description"),
        is_active=row.get("is_active", True),
        member_count=0,
        created_at=str(row["created_at"]),
    )


@router.get("/{group_id}", response_model=GroupResponse)
def get_group(group_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT g.id, g.name, g.group_type, g.leader_id, g.description,
                      g.is_active, g.created_at,
                      m.name AS leader_name,
                      (SELECT COUNT(*) FROM shalenu_small_group_members sgm
                       WHERE sgm.small_group_id = g.id AND sgm.is_active = TRUE) AS member_count
               FROM shalenu_small_groups g
               LEFT JOIN shalenu_members m ON g.leader_id = m.id
               WHERE g.id = %s AND g.church_id = %s""",
            (group_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="구역을 찾을 수 없습니다")
    return _to_group(row)


@router.put("/{group_id}", response_model=GroupResponse)
def update_group(
    group_id: str,
    body: GroupUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [group_id, church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_small_groups SET {set_clause}
                WHERE id = %s AND church_id = %s
                RETURNING id, name, group_type, leader_id, description, is_active, created_at""",
            values,
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="구역을 찾을 수 없습니다")

        leader_name = None
        if row.get("leader_id"):
            cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (row["leader_id"],))
            lm = cur.fetchone()
            if lm:
                leader_name = lm["name"]

        cur.execute(
            "SELECT COUNT(*) AS cnt FROM shalenu_small_group_members WHERE small_group_id = %s AND is_active = TRUE",
            (group_id,),
        )
        member_count = cur.fetchone()["cnt"]

    return GroupResponse(
        id=str(row["id"]),
        name=row["name"],
        group_type=row.get("group_type"),
        leader_id=str(row["leader_id"]) if row.get("leader_id") else None,
        leader_name=leader_name,
        description=row.get("description"),
        is_active=row.get("is_active", True),
        member_count=member_count,
        created_at=str(row["created_at"]),
    )


# ── 구역원 관리 ──────────────────────────────────────────

@router.get("/{group_id}/members", response_model=list[GroupMemberResponse])
def list_group_members(group_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        # 구역이 해당 교회 소속인지 확인
        cur.execute(
            "SELECT id FROM shalenu_small_groups WHERE id = %s AND church_id = %s",
            (group_id, church_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="구역을 찾을 수 없습니다")

        cur.execute(
            """SELECT sgm.id, sgm.member_id, sgm.role, sgm.joined_at, sgm.is_active,
                      m.name AS member_name
               FROM shalenu_small_group_members sgm
               JOIN shalenu_members m ON sgm.member_id = m.id
               WHERE sgm.small_group_id = %s AND sgm.is_active = TRUE
               ORDER BY m.name""",
            (group_id,),
        )
        rows = cur.fetchall()

    return [
        GroupMemberResponse(
            id=str(r["id"]),
            member_id=str(r["member_id"]),
            member_name=r["member_name"],
            role=r["role"],
            joined_at=r.get("joined_at"),
            is_active=r["is_active"],
        )
        for r in rows
    ]


@router.post("/{group_id}/members", response_model=GroupMemberResponse, status_code=status.HTTP_201_CREATED)
def add_group_member(
    group_id: str,
    body: GroupMemberAdd,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM shalenu_small_groups WHERE id = %s AND church_id = %s",
            (group_id, church_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="구역을 찾을 수 없습니다")

        # 이미 등록된 구역원인지 확인
        cur.execute(
            """SELECT id, is_active FROM shalenu_small_group_members
               WHERE small_group_id = %s AND member_id = %s""",
            (group_id, body.member_id),
        )
        existing = cur.fetchone()

        if existing:
            if existing["is_active"]:
                raise HTTPException(status_code=400, detail="이미 등록된 구역원입니다")
            # 비활성 구역원 재활성화
            cur.execute(
                """UPDATE shalenu_small_group_members
                   SET is_active = TRUE, role = %s, joined_at = CURRENT_DATE, left_at = NULL
                   WHERE id = %s
                   RETURNING id, member_id, role, joined_at, is_active""",
                (body.role, existing["id"]),
            )
        else:
            cur.execute(
                """INSERT INTO shalenu_small_group_members (small_group_id, member_id, role)
                   VALUES (%s, %s, %s)
                   RETURNING id, member_id, role, joined_at, is_active""",
                (group_id, body.member_id, body.role),
            )

        row = cur.fetchone()
        cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (body.member_id,))
        member = cur.fetchone()

    return GroupMemberResponse(
        id=str(row["id"]),
        member_id=str(row["member_id"]),
        member_name=member["name"] if member else "",
        role=row["role"],
        joined_at=row.get("joined_at"),
        is_active=row["is_active"],
    )


@router.delete("/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_group_member(
    group_id: str,
    member_id: str,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            "SELECT id FROM shalenu_small_groups WHERE id = %s AND church_id = %s",
            (group_id, church_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="구역을 찾을 수 없습니다")

        cur.execute(
            """UPDATE shalenu_small_group_members
               SET is_active = FALSE, left_at = CURRENT_DATE
               WHERE small_group_id = %s AND member_id = %s AND is_active = TRUE
               RETURNING id""",
            (group_id, member_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="구역원을 찾을 수 없습니다")
