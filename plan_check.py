from fastapi import Depends, HTTPException, status

from db import get_cursor
from dependencies import get_current_user

# 플랜별 허용 기능 집합
PLAN_FEATURES: dict[str, set[str]] = {
    "free":       {"members", "offerings"},
    "growth":     {"members", "offerings", "finance", "community"},
    "community":  {"members", "offerings", "finance", "community", "pastoral"},
    "enterprise": {"members", "offerings", "finance", "community", "pastoral", "all"},
}

PLAN_NAMES = {
    "free": "무료($0)",
    "growth": "성장($49)",
    "community": "공동체($99)",
    "enterprise": "대형($199)",
}

# 기능별 최소 요구 플랜
FEATURE_MIN_PLAN = {
    "finance":   "growth",
    "community": "growth",
    "pastoral":  "community",
}


def require_feature(feature: str):
    """라우터 수준 Depends에 사용할 플랜 체크 의존성 팩토리."""
    def _check(current_user: dict = Depends(get_current_user)) -> None:
        church_id = current_user["church_id"]
        with get_cursor() as cur:
            cur.execute(
                "SELECT plan FROM shalenu_churches WHERE id = %s", (church_id,)
            )
            row = cur.fetchone()
            plan = row["plan"] if row else "free"

        if feature not in PLAN_FEATURES.get(plan, set()):
            required = FEATURE_MIN_PLAN.get(feature, "enterprise")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"이 기능은 '{PLAN_NAMES.get(required, required)}' 요금제 이상에서 사용 가능합니다. "
                    f"현재 요금제: {PLAN_NAMES.get(plan, plan)}"
                ),
            )
    return _check
