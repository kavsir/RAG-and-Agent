import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from src.config.email_config import EmailConfig
import logging

logger = logging.getLogger(__name__)

class EmailSender:
    def __init__(self):
        self.sender = EmailConfig.SENDER_EMAIL
        self.password = EmailConfig.APP_PASSWORD
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        logger.info(f"Initializing EmailSender with sender: {self.sender}")

    def send(self, to, subject, body):
        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender
            msg['To'] = to
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender, self.password)
            server.send_message(msg)
            server.quit()

            logger.info(f"✅ Email sent successfully to {to}")
            return {"success": True, "to": to, "subject": subject}
        except Exception as e:
            logger.error(f"❌ Email sending failed: {e}")
            return {"success": False, "error": str(e)}
def send(self, to, subject, body):
    # Nếu to là list, chuyển thành chuỗi phân cách bằng dấu phẩy
    if isinstance(to, list):
        to = ", ".join(to)
    # ... phần còn lại giữ nguyên