"""
Memory Manager V2: Điều phối các tầng bộ nhớ (Session Memory, Personal Memory, Student Profile và Legacy Vector).
Được thiết kế theo kiến trúc đa tầng (ADR-002), tách bạch Working Memory, Session Memory, Personal Memory.
"""
from typing import Optional, List, Any, Dict
from src.memory.session_memory import SessionMemoryService
from src.memory.personal_memory import PersonalMemoryService
from src.memory.student_memory import StudentMemory
from src.memory.session_models import SessionState, SessionMessage
from src.memory.personal_models import MemoryWriteResult
from src.memory.chat_memory import ChatMemory
from src.memory.vector_memory import VectorMemory


class MemoryManager:
    """
    Điều phối các dịch vụ bộ nhớ:
    - session: SessionMemoryService (SQLite cục bộ, phân vùng theo conversation_id)
    - personal: PersonalMemoryService (SQLite cục bộ, phân vùng theo user_id)
    - legacy_profile: StudentMemory (hồ sơ sinh viên legacy)
    - legacy_chat: ChatMemory (lưu trữ legacy phục vụ tương thích ngược)
    - legacy_vector: VectorMemory (LEGACY / NOT ACTIVE IN SESSION V2)
    """

    def __init__(self):
        self.session = SessionMemoryService()
        self.personal = PersonalMemoryService(store=self.session.store)
        self.legacy_profile = StudentMemory()
        # Giữ thuộc tính profile trỏ về legacy_profile để bảo toàn tương thích ngược
        self.profile = self.legacy_profile
        self.legacy_chat = ChatMemory()
        # LEGACY / NOT ACTIVE IN SESSION V2
        self.legacy_vector = VectorMemory()

        # Thực hiện di chuyển an toàn hồ sơ legacy nếu có (loại bỏ placeholders)
        try:
            self.personal.migrate_legacy_profile(user_id="local-user")
        except Exception:
            pass

    def update(
        self,
        user_message: str,
        ai_message: str,
        conversation_id: Optional[str] = None,
        analyzed_query: Optional[Any] = None,
        sources: Optional[List[Any]] = None,
    ) -> Optional[SessionState]:
        """Cập nhật hội thoại vào phiên tương ứng."""
        state = None
        if conversation_id:
            state = self.session.update_turn(
                conversation_id=conversation_id,
                user_message=user_message,
                ai_message=ai_message,
                analyzed_query=analyzed_query,
                sources=sources,
            )
        else:
            # Fallback legacy chat history nếu không có conversation_id
            self.legacy_chat.add(user_message, ai_message)

        return state

    def get_conversation_history(
        self,
        conversation_id: Optional[str] = None,
        k: int = 5,
    ) -> str:
        """Lấy lịch sử hội thoại có cô lập theo conversation_id."""
        if conversation_id:
            return self.session.get_conversation_history(conversation_id, k=k)
        # Fallback legacy
        history = self.legacy_chat.get_history(k)
        return "\n".join(f"User: {h['user']}\nAI: {h['ai']}" for h in history)

    def get_recent_messages(
        self,
        conversation_id: str,
        k: int = 5,
    ) -> List[SessionMessage]:
        """Lấy danh sách tin nhắn gần nhất của phiên."""
        return self.session.get_recent_messages(conversation_id, k=k)

    def get_session_state(self, conversation_id: str) -> SessionState:
        """Lấy trạng thái thực thể của phiên."""
        return self.session.get_session_state(conversation_id)

    def resolve_context(
        self,
        conversation_id: str,
        current_query: str,
    ):
        """Phân giải thực thể kế thừa từ phiên hội thoại."""
        return self.session.resolve_context(conversation_id, current_query)

    def clear_session(self, conversation_id: str) -> bool:
        """Xóa đúng một phiên hội thoại cụ thể."""
        return self.session.clear_session(conversation_id)

    def clear(self):
        """Xóa legacy chat history (giữ lại các phiên SQLite)."""
        self.legacy_chat.clear()

    # =========================================================================
    # PERSONAL MEMORY DELEGATION
    # =========================================================================
    def get_personal_profile(self, user_id: str = "local-user") -> Dict[str, Any]:
        """Lấy toàn bộ thông tin cá nhân đang hoạt động của người dùng."""
        return self.personal.get_user_profile(user_id=user_id)

    def get_relevant_profile_context(
        self,
        query: str,
        category: str = "DOMAIN_DATA",
        user_id: str = "local-user",
    ) -> Dict[str, Any]:
        """Tiêm ngữ cảnh cá nhân hóa tối thiểu."""
        return self.personal.get_relevant_profile_context(query=query, category=category, user_id=user_id)

    def process_personal_memory(
        self,
        user_id: str,
        message: str,
    ) -> List[MemoryWriteResult]:
        """Trích xuất và xử lý ứng viên sự thật cá nhân từ tin nhắn."""
        return self.personal.process_user_message(user_id=user_id, message=message)

    def set_personal_fact(
        self,
        user_id: str,
        fact_key: str,
        value: Any,
        source_type: str = "PROFILE_API",
    ) -> MemoryWriteResult:
        """Cập nhật một sự thật cá nhân có định kiểu."""
        return self.personal.set_profile_fact(user_id=user_id, fact_key=fact_key, value=value, source_type=source_type)

    def delete_personal_fact(self, user_id: str, fact_key: str) -> bool:
        """Xóa một sự thật cá nhân."""
        return self.personal.delete_fact(user_id=user_id, fact_key=fact_key)

    def clear_personal_memory(self, user_id: str) -> int:
        """Xóa toàn bộ sự thật cá nhân của người dùng."""
        return self.personal.clear_memory(user_id=user_id)


_memory_manager_singleton: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Lấy hoặc khởi tạo Singleton MemoryManager."""
    global _memory_manager_singleton
    if _memory_manager_singleton is None:
        _memory_manager_singleton = MemoryManager()
    return _memory_manager_singleton
