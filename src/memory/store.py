"""
Session Store Interface: Định nghĩa hợp đồng trừu tượng cho tầng lưu trữ phiên làm việc.
Tách biệt hoàn toàn logic nghiệp vụ của LangGraph Agent khỏi cơ sở dữ liệu vật lý.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from src.memory.session_models import SessionRecord, SessionMessage, SessionState
from src.memory.personal_models import PersonalFact, MemoryEvent


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


class PersonalStore(ABC):
    """Giao diện trừu tượng cho kho lưu trữ sự thật cá nhân và kiểm toán vòng đời."""

    @abstractmethod
    def upsert_personal_fact(
        self,
        user_id: str,
        fact_key: str,
        value: Any,
        source_type: str,
        confidence: float = 1.0,
    ) -> PersonalFact:
        """Thêm mới hoặc cập nhật sự thật cá nhân của người dùng."""
        pass

    @abstractmethod
    def get_personal_fact(self, user_id: str, fact_key: str) -> Optional[PersonalFact]:
        """Lấy một sự thật cá nhân đang hoạt động (ACTIVE) theo khóa."""
        pass

    @abstractmethod
    def get_all_personal_facts(self, user_id: str, status: str = "ACTIVE") -> List[PersonalFact]:
        """Lấy tất cả các sự thật cá nhân của người dùng."""
        pass

    @abstractmethod
    def delete_personal_fact(self, user_id: str, fact_key: str) -> bool:
        """Xóa mềm hoặc xóa cứng một sự thật cá nhân cụ thể."""
        pass

    @abstractmethod
    def clear_personal_facts(self, user_id: str) -> int:
        """Xóa toàn bộ sự thật cá nhân của người dùng."""
        pass

    @abstractmethod
    def log_memory_event(
        self,
        user_id: str,
        event_type: str,
        fact_key: str,
        old_value: Optional[Any],
        new_value: Optional[Any],
        source_type: str,
    ) -> MemoryEvent:
        """Ghi nhận nhật ký kiểm toán biến động bộ nhớ."""
        pass

    @abstractmethod
    def get_memory_events(self, user_id: str, limit: int = 50) -> List[MemoryEvent]:
        """Lấy danh sách nhật ký kiểm toán bộ nhớ."""
        pass

