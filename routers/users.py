from fastapi import APIRouter, Depends, HTTPException

from db import get_cursor
from dependencies import get_current_user
from schemas.users import UserListItem, UserUpdate

router = APIRouter(prefix="/api/v1/users", tags=["사용자 관리"])

ALLOWED_ROLES = {"senior_pastor", "associate_pastor", "admin_staff", "admin", "staff", "viewer"}


def _to_user(row: dict, name: str | None = None) -> UserListItem:
    return UserListItem(
        id=str(row["id"]),
        full_name=name or row.get("name"),
        email=row["email"],
        role=row["role"],
        is_active=row.get("is_active", True),
    )


@router.get("", response_model=list[UserListItem])
def list_users(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT u.id, u.email, u.role, u.is_active, u.created_at,
                      m.name
               FROM shalenu_users u
               LEFT JOIN shalenu_members m ON u.member_id = m.id
               WHERE u.church_id = %s
               ORDER BY u.created_at""",
            (church_id,),
        )
        rows = cur.fetchall()

    return [_to_user(r) for r in rows]


@router.put("/{user_id}", response_model=UserListItem)
def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    updates = body.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(status_code=400, detail="수정할 항목이 없습니다")

    if "role" in updates and updates["role"] not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 역할입니다. 허용: {', '.join(ALLOWED_ROLES)}")

    # 자기 자신 비활성화 방지
    if "is_active" in updates and not updates["is_active"] and str(current_user["user_id"]) == user_id:
        raise HTTPException(status_code=400, detail="자기 자신을 비활성화할 수 없습니다")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id, church_id]

    with get_cursor() as cur:
        cur.execute(
            f"""UPDATE shalenu_users SET {set_clause}
                WHERE id = %s AND church_id = %s
                RETURNING id, email, role, is_active, created_at, member_id""",
            values,
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

        name = None
        if row.get("member_id"):
            cur.execute("SELECT name FROM shalenu_members WHERE id = %s", (row["member_id"],))
            m = cur.fetchone()
            if m:
                name = m["name"]

    return _to_user(row, name)
