from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from auth import hash_password, verify_password, create_access_token
from db import get_cursor
from dependencies import get_current_user
from schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["인증"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    with get_cursor() as cur:
        cur.execute("SELECT id FROM shalenu_users WHERE email = %s", (body.email,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다")

        cur.execute(
            """INSERT INTO shalenu_churches (name, address, phone, founded_date, denomination, plan)
               VALUES (%s, %s, %s, %s, %s, 'free') RETURNING id""",
            (body.church_name, body.church_address, body.church_phone, body.founded_date, body.denomination),
        )
        church = cur.fetchone()
        church_id = str(church["id"])

        # 교인(member) 먼저 생성
        cur.execute(
            """INSERT INTO shalenu_members (church_id, name, email, status)
               VALUES (%s, %s, %s, 'active') RETURNING id""",
            (church_id, body.name, body.email),
        )
        member = cur.fetchone()
        member_id = str(member["id"])

        # 사용자(user) 생성 (member_id 연결)
        hashed = hash_password(body.password)
        cur.execute(
            """INSERT INTO shalenu_users (church_id, member_id, email, password_hash, role)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (church_id, member_id, body.email, hashed, body.admin_role),
        )
        user = cur.fetchone()

        # 기본 공통 코드 시드 삽입 (category, code, label, sort_order, parent_code)
        seed_data = [
            ("offering_type", "sunday", "주일헌금", 1, None),
            ("offering_type", "thanksgiving", "감사헌금", 2, None),
            ("offering_type", "tithe", "십일조", 3, None),
            ("offering_type", "mission", "선교헌금", 4, None),
            ("offering_type", "building", "건축헌금", 5, None),
            ("worship_type", "sunday", "주일예배", 1, None),
            ("worship_type", "wednesday", "수요예배", 2, None),
            ("worship_type", "dawn", "새벽예배", 3, None),
            ("worship_type", "special", "특별예배", 4, None),
            ("transaction_category", "worship", "예배", 1, None),
            ("transaction_category", "mission", "선교", 2, None),
            ("transaction_category", "education", "교육", 3, None),
            ("transaction_category", "admin", "행정", 4, None),
            ("transaction_category", "facility", "시설", 5, None),
            ("transaction_category", "etc", "기타", 6, None),
            ("account_type", "checking", "당좌", 1, None),
            ("account_type", "savings", "보통", 2, None),
            ("account_type", "cash", "현금", 3, None),
            # 예산 분류
            ("budget_category", "worship", "예배", 1, None),
            ("budget_category", "mission", "선교", 2, None),
            ("budget_category", "education", "교육", 3, None),
            ("budget_category", "admin", "행정", 4, None),
            ("budget_category", "facility", "시설", 5, None),
            ("budget_category", "etc", "기타", 6, None),
            # 예산 항목 템플릿 (parent_code → budget_category)
            ("budget_item_template", "worship_sound", "음향", 1, "worship"),
            ("budget_item_template", "worship_instrument", "악기", 2, "worship"),
            ("budget_item_template", "worship_bulletin", "주보인쇄", 3, "worship"),
            ("budget_item_template", "mission_overseas", "해외선교", 1, "mission"),
            ("budget_item_template", "mission_domestic", "국내선교", 2, "mission"),
            ("budget_item_template", "edu_textbook", "공과", 1, "education"),
            ("budget_item_template", "edu_teacher", "교사교육", 2, "education"),
            ("budget_item_template", "admin_website", "웹사이트", 1, "admin"),
            ("budget_item_template", "admin_supplies", "사무용품", 2, "admin"),
            ("budget_item_template", "facility_boiler", "보일러", 1, "facility"),
            ("budget_item_template", "facility_electric", "전기", 2, "facility"),
            ("budget_item_template", "facility_cleaning", "청소", 3, "facility"),
            ("budget_item_template", "etc_reserve", "예비비", 1, "etc"),
            # 소그룹 유형
            ("group_type", "district", "구역", 1, None),
            ("group_type", "ranch", "목장", 2, None),
            ("group_type", "cell", "셀", 3, None),
            ("group_type", "department", "부서", 4, None),
            ("group_type", "soon", "순", 5, None),
            ("group_type", "team", "팀", 6, None),
        ]
        for category, code, label, sort_order, parent_code in seed_data:
            cur.execute(
                """INSERT INTO shalenu_lookup_codes (church_id, category, code, label, sort_order, parent_code)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (church_id, category, code, label, sort_order, parent_code),
            )

        token = create_access_token(
            {"sub": str(user["id"]), "church_id": church_id, "email": body.email}
        )
        return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest):
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, church_id, email, password_hash FROM shalenu_users WHERE email = %s",
            (body.email,),
        )
        user = cur.fetchone()
        if not user or not verify_password(body.password, user["password_hash"]):
            raise HTTPException(
                status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다"
            )

        token = create_access_token(
            {
                "sub": str(user["id"]),
                "church_id": str(user["church_id"]),
                "email": user["email"],
            }
        )
        return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    with get_cursor() as cur:
        cur.execute(
            """SELECT u.id, u.church_id, u.email, u.role, m.name
               FROM shalenu_users u
               LEFT JOIN shalenu_members m ON u.member_id = m.id
               WHERE u.id = %s""",
            (current_user["user_id"],),
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        return UserResponse(
            id=str(user["id"]),
            church_id=str(user["church_id"]),
            email=user["email"],
            name=user.get("name"),
            role=user["role"],
        )
