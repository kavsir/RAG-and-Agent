"""
Identity & Principal Context: Định nghĩa thực thể người dùng (Principal) phía máy chủ.
Cung cấp ngữ cảnh danh tính không phụ thuộc vào phương thức xác thực cụ thể,
đảm bảo phân tách ranh giới bảo mật giữa môi trường cục bộ (single-user) và tương lai (multi-tenant).
"""
from pydantic import BaseModel, Field


class PrincipalContext(BaseModel):
    """
    Ngữ cảnh danh tính của người dùng thực hiện yêu cầu.
    Được phân giải hoàn toàn từ phía máy chủ (Server-side resolved).
    """
    user_id: str = Field(default="local-user", description="Định danh người dùng duy nhất phía máy chủ")
    authenticated: bool = Field(default=False, description="Cờ xác nhận danh tính đã được kiểm thực qua JWT/OAuth")
    source: str = Field(default="LOCAL_MODE", description="Nguồn gốc phân giải: LOCAL_MODE | API_KEY | AUTH_TOKEN")

    def is_local(self) -> bool:
        return self.source == "LOCAL_MODE"
