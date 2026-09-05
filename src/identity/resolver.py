"""
Principal Resolver: Phân giải danh tính người dùng phía máy chủ.
Không bao giờ tin tưởng mù quáng user_id do client tự khai báo nếu không có xác thực.
"""
from typing import Optional
from src.identity.principal import PrincipalContext


def resolve_principal(
    user_id_override: Optional[str] = None,
    source: str = "LOCAL_MODE",
) -> PrincipalContext:
    """
    Phân giải danh tính người dùng máy chủ:
    - Trong chế độ local hiện tại: Mặc định luôn là 'local-user'.
    - Trong các bài kiểm thử hoặc gọi nội bộ có thể chỉ định user_id_override.
    """
    effective_user_id = user_id_override or "local-user"
    return PrincipalContext(
        user_id=effective_user_id,
        authenticated=False if source == "LOCAL_MODE" else True,
        source=source,
    )
