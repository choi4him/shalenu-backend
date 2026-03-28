from fastapi import APIRouter, Depends, HTTPException, Query, status

from db import get_cursor
from dependencies import get_current_user
from schemas.messages import MessageCreate, MessageResponse

router = APIRouter(prefix="/api/v1/messages", tags=["메시지 발송"])


@router.get("", response_model=list[MessageResponse])
def list_messages(
    status_filter: str = Query(None, alias="status", description="상태 필터 (draft/sent/failed)"),
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    conditions = ["msg.church_id = %s"]
    params: list = [church_id]

    if status_filter:
        conditions.append("msg.status = %s")
        params.append(status_filter)

    where = " AND ".join(conditions)

    with get_cursor() as cur:
        cur.execute(
            f"""SELECT msg.id, msg.title, msg.content, msg.message_type,
                       msg.sender_id, msg.recipient_type, msg.recipient_ids,
                       msg.status, msg.sent_at, msg.created_at,
                       am.name AS sender_name
                FROM shalenu_messages msg
                JOIN shalenu_users u ON msg.sender_id = u.id
                LEFT JOIN shalenu_members am ON u.member_id = am.id
                WHERE {where}
                ORDER BY msg.created_at DESC""",
            params,
        )
        rows = cur.fetchall()

    return [_to_response(r) for r in rows]


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_message(body: MessageCreate, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]
    user_id = str(current_user["user_id"])

    sent_at = None
    msg_status = body.status
    if msg_status == "sent":
        sent_at = "NOW()"

    with get_cursor() as cur:
        if sent_at:
            cur.execute(
                """INSERT INTO shalenu_messages
                   (church_id, title, content, message_type, sender_id,
                    recipient_type, recipient_ids, status, sent_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                   RETURNING id, title, content, message_type, sender_id,
                             recipient_type, recipient_ids, status, sent_at, created_at""",
                (church_id, body.title, body.content, body.message_type,
                 user_id, body.recipient_type, body.recipient_ids, msg_status),
            )
        else:
            cur.execute(
                """INSERT INTO shalenu_messages
                   (church_id, title, content, message_type, sender_id,
                    recipient_type, recipient_ids, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, title, content, message_type, sender_id,
                             recipient_type, recipient_ids, status, sent_at, created_at""",
                (church_id, body.title, body.content, body.message_type,
                 user_id, body.recipient_type, body.recipient_ids, msg_status),
            )
        row = cur.fetchone()

        cur.execute(
            """SELECT am.name FROM shalenu_users u
               LEFT JOIN shalenu_members am ON u.member_id = am.id
               WHERE u.id = %s""",
            (user_id,),
        )
        sender = cur.fetchone()

    result = dict(row)
    result["sender_name"] = sender["name"] if sender else None
    return _to_response(result)


@router.get("/{message_id}", response_model=MessageResponse)
def get_message(message_id: str, current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT msg.id, msg.title, msg.content, msg.message_type,
                      msg.sender_id, msg.recipient_type, msg.recipient_ids,
                      msg.status, msg.sent_at, msg.created_at,
                      am.name AS sender_name
               FROM shalenu_messages msg
               JOIN shalenu_users u ON msg.sender_id = u.id
               LEFT JOIN shalenu_members am ON u.member_id = am.id
               WHERE msg.id = %s AND msg.church_id = %s""",
            (message_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    return _to_response(row)


def _to_response(row: dict) -> MessageResponse:
    recipient_ids = row.get("recipient_ids")
    if recipient_ids:
        recipient_ids = [str(rid) for rid in recipient_ids]

    return MessageResponse(
        id=str(row["id"]),
        title=row["title"],
        content=row["content"],
        message_type=row["message_type"],
        sender_id=str(row["sender_id"]),
        sender_name=row.get("sender_name"),
        recipient_type=row["recipient_type"],
        recipient_ids=recipient_ids,
        status=row["status"],
        sent_at=str(row["sent_at"]) if row.get("sent_at") else None,
        created_at=str(row["created_at"]),
    )
