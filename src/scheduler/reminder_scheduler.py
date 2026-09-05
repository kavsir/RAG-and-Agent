"""
Reminder Scheduler: Quản lý tác vụ nhắc nhở với APScheduler theo vòng đời Backend Lifespan.
Không tự động kích hoạt khi import module.
"""
import datetime
import logging
from typing import Callable, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore

logger = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        jobstores = {"default": MemoryJobStore()}
        _scheduler = BackgroundScheduler(jobstores=jobstores)
    return _scheduler


def start_scheduler():
    """Khởi động scheduler (chỉ nên gọi trong FastAPI lifespan)."""
    sched = get_scheduler()
    if not sched.running:
        try:
            sched.start()
            logger.info("APScheduler da khoi dong thanh cong.")
        except Exception as e:
            logger.error(f"Loi khi khoi dong scheduler: {e}")


def shutdown_scheduler():
    """Dừng scheduler một cách an toàn khi tắt ứng dụng."""
    global _scheduler
    if _scheduler and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("APScheduler da dung.")
        except Exception as e:
            logger.error(f"Loi khi tat scheduler: {e}")


def schedule_reminder(run_date: datetime.datetime, func: Callable, args: list) -> Optional[str]:
    """Lên lịch nhắc nhở một lần."""
    sched = get_scheduler()
    if not sched.running:
        start_scheduler()

    try:
        job = sched.add_job(func, "date", run_date=run_date, args=args)
        logger.info(f"Da len lich nhắc tai {run_date} voi job_id {job.id}")
        return job.id
    except Exception as e:
        logger.error(f"Loi khi them job vao scheduler: {e}")
        return None
