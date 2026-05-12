from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
import datetime
import logging

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sử dụng MemoryJobStore (job sẽ mất khi restart app)
jobstores = {
    'default': MemoryJobStore()
}
scheduler = BackgroundScheduler(jobstores=jobstores)

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shutdown")

def schedule_reminder(run_date: datetime.datetime, func, args):
    """
    Thêm job vào scheduler
    run_date: thời điểm chạy
    func: hàm cần gọi (ví dụ: gửi email)
    args: tham số cho func
    """
    job = scheduler.add_job(func, 'date', run_date=run_date, args=args)
    logger.info(f"Job scheduled at {run_date} with id {job.id}")
    return job.id