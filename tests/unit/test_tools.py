from src.tools.email_sender import EmailSender
from src.scheduler.reminder_scheduler import get_scheduler, start_scheduler, shutdown_scheduler
from src.agent.nodes import parse_reminder_node, parse_email_node
from src.config.settings import settings


def test_email_sender_disabled_fallback():
    sender = EmailSender()
    sender.enabled = False
    res = sender.send("test@example.com", "Subject", "Body")
    assert res["success"] is False
    assert "Chức năng email hiện chưa được cấu hình." in res["error"]


def test_scheduler_lifecycle():
    sched = get_scheduler()
    assert sched is not None
    start_scheduler()
    assert sched.running is True
    shutdown_scheduler()


def test_reminder_node_creates_real_job():
    sched = get_scheduler()
    # Xóa các jobs cũ nếu có
    for j in sched.get_jobs():
        j.remove()
    assert len(sched.get_jobs()) == 0

    query = "Nhắc tôi nộp bài tập lớn môn Hệ thống nhúng vào lúc 17h ngày 20/12/2026"
    res = parse_reminder_node({"question": query})

    assert res.get("reminder_request") is not None
    req = res["reminder_request"]
    assert "content" in req
    assert "scheduled_at" in req
    assert "job_id" in req

    # Kiểm tra job thực tế đã được lưu trong APScheduler
    jobs = sched.get_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == req["job_id"]
    assert "20/12/2026 17:00" in req["scheduled_at"]
    assert "Đã lên lịch nhắc nhở thành công" in res["answer"]

    # Dọn dẹp job sau khi kiểm thử
    job.remove()
    assert len(sched.get_jobs()) == 0


def test_reminder_node_insufficient_time_info():
    sched = get_scheduler()
    jobs_before = len(sched.get_jobs())

    # Câu hỏi không chứa thông tin ngày giờ
    res = parse_reminder_node({"question": "Nhắc tôi ôn thi môn AI"})

    # Không tự bịa thời gian, yêu cầu người dùng bổ sung
    assert res["reminder_request"] is None
    assert "Vui lòng cung cấp ngày hoặc giờ cụ thể" in res["answer"]
    assert len(sched.get_jobs()) == jobs_before


def test_email_safety_no_recipient():
    # Khi bật EMAIL_ENABLED nhưng người dùng không cung cấp email
    old_status = settings.EMAIL_ENABLED
    settings.EMAIL_ENABLED = True
    try:
        res = parse_email_node({"question": "Gửi email cho thầy giáo môn FIT4113 để xin tài liệu"})
        # Không được fallback student@dainam.edu.vn, phải yêu cầu email
        assert "student@dainam.edu.vn" not in res.get("answer", "")
        assert "Vui lòng cung cấp địa chỉ email người nhận hợp lệ" in res["answer"]
    finally:
        settings.EMAIL_ENABLED = old_status
