"""
Email Sender Tool: Gui email qua SMTP voi co che kiem tra EMAIL_ENABLED an toan.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Union, List, Dict, Any

from src.config.settings import settings

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self):
        self.enabled = settings.EMAIL_ENABLED
        self.sender = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.smtp_server = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT

    def send(self, to: Union[str, List[str]], subject: str, body: str) -> Dict[str, Any]:
        """Gửi email nếu EMAIL_ENABLED=True, nếu không thì trả về thông báo an toàn."""
        if not self.enabled:
            logger.info("Chức năng email bị tắt (EMAIL_ENABLED=false). Bỏ qua gửi email.")
            return {"success": False, "error": "Chức năng email hiện chưa được cấu hình."}

        if not self.sender or not self.password:
            return {"success": False, "error": "Chưa cấu hình tài khoản SMTP (SMTP_USER hoặc SMTP_PASSWORD)."}

        if isinstance(to, list):
            to_str = ", ".join(to)
            recipients = to
        else:
            to_str = to
            recipients = [to]

        try:
            msg = MIMEMultipart()
            msg["From"] = self.sender
            msg["To"] = to_str
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
            server.starttls()
            server.login(self.sender, self.password)
            server.send_message(msg, to_addrs=recipients)
            server.quit()

            logger.info(f"Email da gui thanh cong den {to_str}")
            return {"success": True, "to": to_str, "subject": subject}
        except Exception as e:
            logger.error(f"Loi khi gui email den {to_str}: {e}")
            return {"success": False, "error": str(e)}


def send_email_direct(to: Union[str, List[str]], subject: str, body: str) -> Dict[str, Any]:
    """Hàm tiện ích gửi email trực tiếp qua EmailSender."""
    sender = EmailSender()
    return sender.send(to=to, subject=subject, body=body)
