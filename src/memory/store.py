"""
Session Store Interface: Định nghĩa hợp đồng trừu tượng cho tầng lưu trữ phiên làm việc.
Tách biệt hoàn toàn logic nghiệp vụ của LangGraph Agent khỏi cơ sở dữ liệu vật lý.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from src.memory.session_models import SessionRecord, SessionMessage, SessionState


class SessionStore(ABC):
    """Giao diện trừu tượng cho kho lưu trữ phiên hội thoại."""

    @abstractmethod
    def create_session(
        self,
        conversation_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionRecord:
        """Tạo một phiên hội thoại mới nếu chưa tồn tại."""
        pass

    @abstractmethod
    def get_session(self, conversation_id: str) -> Optional[SessionRecord]:
        """Lấy thông tin phiên hội thoại theo ID."""
        pass

    @abstractmethod
    def touch_session(self, conversation_id: str) -> None:
        """Cập nhật thời điểm hoạt động gần nhất (last_activity_at)."""
        pass

    @abstractmethod
    def get_session_state(self, conversation_id: str) -> SessionState:
        """Lấy trạng thái thực thể có cấu trúc của phiên (SessionState)."""
        pass

    @abstractmethod
    def update_session_state(self, state: SessionState) -> None:
        """Cập nhật trạng thái thực thể của phiên."""
        pass

    @abstractmethod
    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> SessionMessage:
        """Lưu thêm một tin nhắn vào lịch sử của phiên tương ứng."""
        pass

    @abstractmethod
    def get_recent_messages(
        self,
        conversation_id: str,
        k: int = 5,
    ) -> List[SessionMessage]:
        """Lấy k tin nhắn gần nhất thuộc đúng phiên hội thoại."""
        pass

    @abstractmethod
    def clear_session(self, conversation_id: str) -> bool:
        """Xóa toàn bộ tin nhắn và reset trạng thái của một phiên (giữ lại bản ghi phiên)."""
        pass

    @abstractmethod
    def delete_session(self, conversation_id: str) -> bool:
        """Xóa hoàn toàn phiên hội thoại và mọi dữ liệu liên quan."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Đóng kết nối kho lưu trữ an toàn."""
        pass
