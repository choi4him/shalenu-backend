from pydantic import BaseModel
from typing import Optional, List


class MessageCreate(BaseModel):
    title: str
    content: str
    message_type: str  # sms, email
    recipient_type: str  # all, group, individual
    recipient_ids: Optional[List[str]] = None
    status: str = "draft"  # draft, sent


class MessageResponse(BaseModel):
    id: str
    title: str
    content: str
    message_type: str
    sender_id: str
    sender_name: Optional[str] = None
    recipient_type: str
    recipient_ids: Optional[List[str]] = None
    status: str
    sent_at: Optional[str] = None
    created_at: str
