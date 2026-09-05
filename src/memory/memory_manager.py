"""
Memory Manager V2: Điều phối các tầng bộ nhớ (Session Memory, Student Profile và Legacy Vector).
Được thiết kế theo cấu trúc module để sẵn sàng tích hợp Personal Memory và Episodic Memory trong tương lai.
"""
from typing import Optional, List, Any
from src.memory.session_memory import SessionMemoryService
from src.memory.student_memory import StudentMemory
from src.memory.session_models import SessionState, SessionMessage
from src.memory.chat_memory import ChatMemory
from src.memory.vector_memory import VectorMemory


class MemoryManager:
    """
    Điều phối các dịch vụ bộ nhớ:
    - session: SessionMemoryService (SQLite cục bộ, phân vùng theo conversation_id)
    - profile: StudentMemory (hồ sơ sinh viên cá nhân hóa)
    - legacy_chat: ChatMemory (lưu trữ legacy phục vụ tương thích ngược)
    - legacy_vector: VectorMemory (LEGACY / NOT ACTIVE IN SESSION V2)
    """

    def __init__(self):
        self.session = SessionMemoryService()
        self.profile = StudentMemory()
        self.legacy_chat = ChatMemory()
        # LEGACY / NOT ACTIVE IN SESSION V2
        self.legacy_vector = VectorMemory()

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


_memory_manager_singleton: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Lấy hoặc khởi tạo Singleton MemoryManager."""
    global _memory_manager_singleton
    if _memory_manager_singleton is None:
        _memory_manager_singleton = MemoryManager()
    return _memory_manager_singleton
