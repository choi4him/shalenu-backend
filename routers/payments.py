from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
import os
import json
import hmac
import hashlib

import requests as http_requests

from db import get_cursor
from dependencies import get_current_user
from schemas.payments import (
    PaymentLinkCreate, KoreaPaymentLinkCreate, PaymentLinkResponse,
    OnlinePaymentResponse,
)

router = APIRouter(prefix="/api/v1/payments", tags=["온라인 헌금"])


def _get_stripe():
    """Stripe 클라이언트 반환 (키 미설정 시 503 오류)"""
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key or not key.startswith("sk_"):
        raise HTTPException(
            status_code=503,
            detail="Stripe가 설정되지 않았습니다. STRIPE_SECRET_KEY를 .env에 추가해주세요.",
        )
    try:
        import stripe as _stripe
        _stripe.api_key = key
        return _stripe
    except ImportError:
        raise HTTPException(status_code=503, detail="stripe 패키지가 설치되지 않았습니다.")


# ── 결제 링크 목록 ──────────────────────────────────────

@router.get("/payment-links", response_model=list[PaymentLinkResponse])
def list_payment_links(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT id, title, description, amount, currency, provider,
                      stripe_price_id, stripe_link_id, stripe_link_url,
                      portone_link_id, portone_link_url,
                      is_active, created_at
               FROM shalenu_payment_links
               WHERE church_id = %s
               ORDER BY created_at DESC""",
            (church_id,),
        )
        rows = cur.fetchall()

    return [_to_link(r) for r in rows]


# ── 결제 링크 생성 ──────────────────────────────────────

@router.post("/payment-links", response_model=PaymentLinkResponse, status_code=status.HTTP_201_CREATED)
def create_payment_link(
    body: PaymentLinkCreate,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]
    user_id = str(current_user["user_id"])
    stripe = _get_stripe()

    try:
        # Stripe Price 생성 (금액 고정 or 자유 금액)
        if body.amount:
            price = stripe.Price.create(
                unit_amount=body.amount,
                currency=body.currency,
                product_data={"name": body.title},
            )
        else:
            price = stripe.Price.create(
                currency=body.currency,
                custom_unit_amount={"enabled": True},
                product_data={"name": body.title},
            )

        # Stripe Payment Link 생성
        link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            payment_intent_data={
                "metadata": {"church_id": str(church_id)},
            },
        )

        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO shalenu_payment_links
                   (church_id, title, description, amount, currency,
                    stripe_price_id, stripe_link_id, stripe_link_url, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, title, description, amount, currency,
                             stripe_price_id, stripe_link_id, stripe_link_url,
                             is_active, created_at""",
                (
                    church_id, body.title, body.description, body.amount,
                    body.currency, price.id, link.id, link.url, user_id,
                ),
            )
            row = cur.fetchone()

        return _to_link(row)

    except Exception as e:
        error_msg = str(e)
        if "stripe" in error_msg.lower() or hasattr(e, "http_status"):
            raise HTTPException(status_code=400, detail=f"Stripe 오류: {error_msg}")
        raise


# ── 결제 링크 활성화/비활성화 토글 ──────────────────────

@router.patch("/payment-links/{link_id}/toggle")
def toggle_payment_link(
    link_id: str,
    current_user: dict = Depends(get_current_user),
):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """UPDATE shalenu_payment_links
               SET is_active = NOT is_active
               WHERE id = %s AND church_id = %s
               RETURNING id, stripe_link_id, is_active""",
            (link_id, church_id),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="결제 링크를 찾을 수 없습니다")

    # Stripe와 동기화 (선택적 — 실패해도 DB 상태 유지)
    if row["stripe_link_id"]:
        try:
            stripe = _get_stripe()
            stripe.PaymentLink.modify(row["stripe_link_id"], active=row["is_active"])
        except Exception:
            pass  # Stripe 동기화 실패는 무시

    return {"id": str(row["id"]), "is_active": row["is_active"]}


# ── 온라인 헌금 내역 ────────────────────────────────────

@router.get("/online-payments", response_model=list[OnlinePaymentResponse])
def list_online_payments(current_user: dict = Depends(get_current_user)):
    church_id = current_user["church_id"]

    with get_cursor() as cur:
        cur.execute(
            """SELECT p.id, p.payment_link_id, pl.title AS link_title,
                      p.donor_name, p.donor_email, p.amount, p.currency,
                      p.status, p.paid_at, p.created_at
               FROM shalenu_online_payments p
               LEFT JOIN shalenu_payment_links pl ON p.payment_link_id = pl.id
               WHERE p.church_id = %s
               ORDER BY p.created_at DESC
               LIMIT 200""",
            (church_id,),
        )
        rows = cur.fetchall()

    return [_to_payment(r) for r in rows]


# ── Stripe Webhook ──────────────────────────────────────

@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    """Stripe 결제 완료 웹훅 — 인증 불필요"""
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    payload = await request.body()

    try:
        import stripe as _stripe
        _stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

        if webhook_secret:
            event = _stripe.Webhook.construct_event(payload, stripe_signature, webhook_secret)
        else:
            # 개발 환경: 서명 검증 없이 파싱
            import json
            event = json.loads(payload)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook 오류: {str(e)}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        payment_link_stripe_id = session.get("payment_link")

        if payment_link_stripe_id:
            with get_cursor() as cur:
                # 결제 링크 DB 레코드 조회
                cur.execute(
                    "SELECT id, church_id FROM shalenu_payment_links WHERE stripe_link_id = %s",
                    (payment_link_stripe_id,),
                )
                link_row = cur.fetchone()

                if link_row:
                    customer = session.get("customer_details") or {}
                    cur.execute(
                        """INSERT INTO shalenu_online_payments
                           (church_id, payment_link_id, stripe_session_id,
                            donor_name, donor_email, amount, currency, status, paid_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, 'completed', NOW())
                           ON CONFLICT (stripe_session_id) DO NOTHING""",
                        (
                            str(link_row["church_id"]),
                            str(link_row["id"]),
                            session["id"],
                            customer.get("name"),
                            customer.get("email"),
                            session.get("amount_total", 0),
                            session.get("currency", "usd"),
                        ),
                    )

    return {"received": True}


# ── PortOne 한국 결제 링크 생성 ────────────────────────

@router.post("/korea/create-link", response_model=PaymentLinkResponse, status_code=status.HTTP_201_CREATED)
def create_korea_payment_link(
    body: KoreaPaymentLinkCreate,
    current_user: dict = Depends(get_current_user),
):
    """PortOne V2 결제 링크 생성 (KRW)"""
    api_secret = os.getenv("PORTONE_API_SECRET", "")
    if not api_secret or api_secret == "나중에추가":
        raise HTTPException(
            status_code=503,
            detail="PortOne이 설정되지 않았습니다. PORTONE_API_SECRET를 .env에 추가해주세요.",
        )

    church_id = current_user["church_id"]
    user_id = str(current_user["user_id"])

    # PortOne V2 결제 링크 생성 API
    payload: dict = {
        "title": body.title,
        "currency": "KRW",
        "payMethods": [{"payMethod": "CARD"}, {"payMethod": "TRANSFER"}],
    }
    if body.amount:
        payload["amount"] = {"total": body.amount}

    resp = http_requests.post(
        "https://api.portone.io/payment-links",
        headers={
            "Authorization": f"PortOne {api_secret}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )

    if not resp.ok:
        raise HTTPException(
            status_code=400,
            detail=f"PortOne 오류: {resp.status_code} {resp.text}",
        )

    data = resp.json()
    portone_link_id = data.get("paymentLinkId") or data.get("id")
    portone_link_url = data.get("url") or data.get("shortUrl")

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO shalenu_payment_links
               (church_id, title, description, amount, currency, provider,
                portone_link_id, portone_link_url, created_by)
               VALUES (%s, %s, %s, %s, 'krw', 'portone', %s, %s, %s)
               RETURNING id, title, description, amount, currency, provider,
                         stripe_price_id, stripe_link_id, stripe_link_url,
                         portone_link_id, portone_link_url,
                         is_active, created_at""",
            (
                church_id, body.title, body.description, body.amount,
                portone_link_id, portone_link_url, user_id,
            ),
        )
        row = cur.fetchone()

    return _to_link(row)


# ── PortOne 웹훅 ────────────────────────────────────────

@router.post("/korea/webhook")
async def portone_webhook(request: Request):
    """PortOne 결제 완료 웹훅 → shalenu_online_payments + shalenu_offering_items 자동 등록"""
    payload_bytes = await request.body()

    # 웹훅 서명 검증 (PORTONE_API_SECRET으로 HMAC-SHA256)
    api_secret = os.getenv("PORTONE_API_SECRET", "")
    webhook_signature = request.headers.get("webhook-signature", "")
    if api_secret and api_secret != "나중에추가" and webhook_signature:
        # PortOne V2 웹훅 서명: t=timestamp,v1=signature
        try:
            parts = dict(item.split("=", 1) for item in webhook_signature.split(","))
            timestamp = parts.get("t", "")
            expected = hmac.new(
                api_secret.encode(),
                (timestamp + "." + payload_bytes.decode()).encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, parts.get("v1", "")):
                raise HTTPException(status_code=400, detail="웹훅 서명이 올바르지 않습니다")
        except HTTPException:
            raise
        except Exception:
            pass  # 개발 환경에서는 검증 실패 무시

    try:
        event = json.loads(payload_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="웹훅 파싱 오류")

    event_type = event.get("type") or event.get("status")

    # Transaction.Paid 이벤트 처리
    if event_type in ("Transaction.Paid", "paid"):
        tx = event.get("data") or event
        imp_uid = tx.get("impUid") or tx.get("paymentId") or tx.get("id")
        portone_link_id = tx.get("paymentLinkId") or tx.get("customData", {}).get("paymentLinkId")
        donor_name = tx.get("customer", {}).get("name") or tx.get("buyerName")
        donor_email = tx.get("customer", {}).get("email") or tx.get("buyerEmail")
        amount_total = tx.get("amount", {}).get("total") if isinstance(tx.get("amount"), dict) else tx.get("amount", 0)

        if not imp_uid:
            return {"received": True}

        with get_cursor() as cur:
            # portone_link_id로 DB 링크 조회
            link_row = None
            if portone_link_id:
                cur.execute(
                    "SELECT id, church_id FROM shalenu_payment_links WHERE portone_link_id = %s",
                    (portone_link_id,),
                )
                link_row = cur.fetchone()

            church_id = str(link_row["church_id"]) if link_row else None
            link_db_id = str(link_row["id"]) if link_row else None

            # 온라인 결제 내역 저장
            if church_id:
                cur.execute(
                    """INSERT INTO shalenu_online_payments
                       (church_id, payment_link_id, portone_imp_uid,
                        donor_name, donor_email, amount, currency, status, paid_at)
                       VALUES (%s, %s, %s, %s, %s, %s, 'krw', 'completed', NOW())
                       ON CONFLICT (portone_imp_uid) DO NOTHING
                       RETURNING id""",
                    (church_id, link_db_id, imp_uid, donor_name, donor_email, amount_total),
                )
                payment_row = cur.fetchone()

                # shalenu_offerings + shalenu_offering_items 자동 등록
                if payment_row and amount_total:
                    cur.execute(
                        """INSERT INTO shalenu_offerings
                           (church_id, offering_date, offering_type, worship_type,
                            total_amount, status, created_by)
                           VALUES (%s, CURRENT_DATE, 'online', 'online', %s, 'confirmed', NULL)
                           RETURNING id""",
                        (church_id, amount_total),
                    )
                    offering_row = cur.fetchone()
                    if offering_row:
                        cur.execute(
                            """INSERT INTO shalenu_offering_items
                               (offering_id, member_id, giver_name, amount, payment_method, note)
                               VALUES (%s, NULL, %s, %s, 'online', %s)""",
                            (
                                str(offering_row["id"]),
                                donor_name or "온라인 기부",
                                amount_total,
                                f"PortOne 결제 ({imp_uid})",
                            ),
                        )

    return {"received": True}


# ── 헬퍼 ───────────────────────────────────────────────

def _to_link(row: dict) -> PaymentLinkResponse:
    return PaymentLinkResponse(
        id=str(row["id"]),
        title=row["title"],
        description=row.get("description"),
        amount=row.get("amount"),
        currency=row.get("currency", "usd"),
        provider=row.get("provider", "stripe"),
        stripe_price_id=row.get("stripe_price_id"),
        stripe_link_id=row.get("stripe_link_id"),
        stripe_link_url=row.get("stripe_link_url"),
        portone_link_id=row.get("portone_link_id"),
        portone_link_url=row.get("portone_link_url"),
        is_active=row.get("is_active", True),
        created_at=str(row["created_at"]),
    )


def _to_payment(row: dict) -> OnlinePaymentResponse:
    return OnlinePaymentResponse(
        id=str(row["id"]),
        payment_link_id=str(row["payment_link_id"]) if row.get("payment_link_id") else None,
        link_title=row.get("link_title"),
        donor_name=row.get("donor_name"),
        donor_email=row.get("donor_email"),
        amount=row["amount"],
        currency=row.get("currency", "usd"),
        status=row["status"],
        paid_at=str(row["paid_at"]) if row.get("paid_at") else None,
        created_at=str(row["created_at"]),
    )
