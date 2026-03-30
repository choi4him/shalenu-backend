import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from db import get_cursor
from routers.backup import _generate_backup, _send_backup_email, _next_backup_at

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()


def run_scheduled_backups() -> None:
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    logger.info(f"[scheduler] 백업 확인 실행: {now.isoformat()}")

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, church_id, send_to_email, frequency
            FROM shalenu_backup_settings
            WHERE is_enabled = TRUE
              AND next_backup_at IS NOT NULL
              AND next_backup_at <= %s
            """,
            (now,),
        )
        rows = cur.fetchall() or []

    for row in rows:
        church_id = str(row["church_id"])
        send_to = row["send_to_email"]
        frequency = row["frequency"]
        setting_id = str(row["id"])
        try:
            json_str, church_name = _generate_backup(church_id)
            _send_backup_email(send_to, church_name, json_str, date_str)

            next_at = _next_backup_at(frequency, now)
            with get_cursor() as cur2:
                cur2.execute(
                    """
                    UPDATE shalenu_backup_settings
                    SET last_backup_at = %s, next_backup_at = %s
                    WHERE id = %s
                    """,
                    (now, next_at, setting_id),
                )
            logger.info(f"[scheduler] 백업 이메일 발송 완료 church={church_id}, 다음={next_at.isoformat()}")
        except Exception as exc:
            logger.error(f"[scheduler] 백업 실패 church={church_id}: {exc}")


def start_scheduler() -> None:
    _scheduler.add_job(
        run_scheduled_backups,
        "cron",
        hour=0,
        minute=0,
        id="daily_backup",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("[scheduler] APScheduler 시작됨")


def stop_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
    logger.info("[scheduler] APScheduler 중지됨")
