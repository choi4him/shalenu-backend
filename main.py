from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from db import init_pool, close_pool, get_cursor
from scheduler import start_scheduler, stop_scheduler
from routers import (
    auth, members, offerings, finance, lookup, churches, users,
    worship, groups, attendance, pledges, newcomers,
    pastoral_notes, messages, birthdays, facilities, payments, backup,
)

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_pool()
    start_scheduler()
    yield
    stop_scheduler()
    close_pool()


app = FastAPI(
    title="J-SheepFold API",
    description="교회 통합 관리 시스템 — J-SheepFold",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://shalenu-frontend.vercel.app",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(members.router)
app.include_router(offerings.router)
app.include_router(finance.router)
app.include_router(lookup.router)
app.include_router(churches.router)
app.include_router(users.router)
app.include_router(worship.router)
app.include_router(groups.router)
app.include_router(attendance.router)
app.include_router(pledges.router)
app.include_router(newcomers.router)
app.include_router(pastoral_notes.router)
app.include_router(messages.router)
app.include_router(birthdays.router)
app.include_router(facilities.router)
app.include_router(payments.router)
app.include_router(backup.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/admin/fix-plan")
def fix_plan(secret: str):
    """임시 엔드포인트: 테스트교회 플랜 업데이트 (1회 사용 후 삭제 예정)"""
    if secret != "shalenu-fix-2026":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden")
    with get_cursor() as cur:
        cur.execute(
            "UPDATE shalenu_churches SET plan = 'community' WHERE name = '테스트교회' RETURNING id, name, plan"
        )
        rows = cur.fetchall()
    return {"updated": [dict(r) for r in rows]}
