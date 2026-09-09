"""
Session Memory Service: Dịch vụ điều phối bộ nhớ phiên có cấu trúc (SessionMemoryService).
Thực thi chính sách giải quyết đại từ thay thế tất định, chuyển đổi thực thể,
kế thừa mục tiêu và cô lập ngữ cảnh triệt để theo từng conversation_id.
"""
import re
import logging
from typing import Optional, Any, List, Tuple
from src.memory.store import SessionStore
from src.memory.sqlite_store import SQLiteSessionStore
from src.memory.session_models import SessionState, SessionMessage, SessionRecord

logger = logging.getLogger(__name__)


class SessionMemoryService:
    """
    Dịch vụ quản lý bộ nhớ phiên hội thoại có cấu trúc.
    """

    def __init__(self, store: Optional[SessionStore] = None):
        self.store = store or SQLiteSessionStore()

    def get_session(self, conversation_id: str) -> Optional[SessionRecord]:
        """Lấy thông tin phiên hội thoại."""
        return self.store.get_session(conversation_id)

    def get_session_state(self, conversation_id: str) -> SessionState:
        """Lấy trạng thái thực thể của phiên."""
        return self.store.get_session_state(conversation_id)

    def get_recent_messages(
        self,
        conversation_id: str,
        k: int = 5,
    ) -> List[SessionMessage]:
        """Lấy danh sách tin nhắn gần nhất của phiên."""
        return self.store.get_recent_messages(conversation_id, k=k)

    def get_conversation_history(
        self,
        conversation_id: str,
        k: int = 5,
    ) -> str:
        """Định dạng lịch sử hội thoại thành chuỗi văn bản cho Prompt/Agent."""
        messages = self.get_recent_messages(conversation_id, k=k)
        if not messages:
            return ""
        formatted = []
        for m in messages:
            prefix = "User" if m.role == "user" else "AI"
            formatted.append(f"{prefix}: {m.content}")
        return "\n".join(formatted)

    def resolve_context(
        self,
        conversation_id: str,
        current_query: str,
    ) -> Tuple[Optional[str], Optional[str], str, bool]:
        """
        Phân giải ngữ cảnh thực thể và mục tiêu tất định:
        Returns:
            (resolved_course_code, resolved_target, resolution_source, unresolved_reference)
            - resolution_source: "EXPLICIT" | "SESSION" | "UNRESOLVED" | "NONE"
        """
        # 1. Kiểm tra mã môn học tường minh trong câu hỏi hiện tại
        code_match = re.search(r"\b([A-Z]{2,4}\d{4})\b", current_query, re.IGNORECASE)
        if code_match:
            explicit_code = code_match.group(1).upper()
            return explicit_code, None, "EXPLICIT", False

        # 2. Kiểm tra đại từ thay thế hoặc câu hỏi kế thừa ngữ cảnh
        q_lower = current_query.lower()
        pronoun_patterns = [
            r"\bmôn đó\b", r"\bmôn này\b", r"\bmôn đấy\b", r"\bhọc phần đó\b",
            r"\bhọc phần này\b", r"\bmôn trên\b", r"\bhọc phần trên\b",
            r"\b(nó|môn đó|học phần đó)\b", r"\bkỳ đó\b",
            r"\bmôn vừa rồi\b", r"\bmôn học đó\b", r"\bmôn học này\b", r"\bmôn ấy\b"
        ]
        has_pronoun = any(re.search(p, q_lower) for p in pronoun_patterns)

        # Câu hỏi follow-up ngắn không chứa chủ ngữ nhưng hỏi về giảng viên, email, tín chỉ...
        implicit_followup_cues = [
            "ai dạy", "ai là người dạy", "ai phụ trách", "phụ trách", "thầy nào", "cô nào", "email", "mail",
            "mấy tín", "bao nhiêu tín", "số tín", "tín chỉ", "chuẩn đầu ra", "clo", "đề cương",
            "kế hoạch", "học phí", "chuyên cần", "thi kết thúc", "tiên quyết", "học trước",
            "điều kiện", "kỳ nào", "học kỳ nào", "vào kỳ"
        ]

        def _matches(kw: str, text: str) -> bool:
            if len(kw.split()) == 1 and len(kw) <= 4:
                return bool(re.search(rf"\b{re.escape(kw)}\b", text))
            return kw in text

        has_implicit_cue = any(_matches(cue, q_lower) for cue in implicit_followup_cues)

        if has_pronoun or has_implicit_cue:
            state = self.get_session_state(conversation_id)
            active_entity = state.active_course_code or state.last_academic_entity
            if active_entity:
                # Kế thừa mục tiêu (target carry-over)
                resolved_target = None
                if ("email" in q_lower or "mail" in q_lower) and state.active_target == "lecturer":
                    resolved_target = "lecturer_email"
                elif _matches("email", q_lower) or _matches("mail", q_lower):
                    resolved_target = "lecturer_email"
                elif any(_matches(kw, q_lower) for kw in ["ai dạy", "ai là người dạy", "ai phụ trách", "thầy nào", "cô nào", "giảng viên"]):
                    resolved_target = "lecturer"
                elif any(_matches(kw, q_lower) for kw in ["mấy tín", "bao nhiêu tín", "số tín", "tín chỉ"]):
                    resolved_target = "credits"
                elif any(_matches(kw, q_lower) for kw in ["tiên quyết", "học trước"]):
                    resolved_target = "prerequisites"
                elif any(_matches(kw, q_lower) for kw in ["chuẩn đầu ra", "clo", "đề cương"]):
                    resolved_target = "clo"
                elif any(_matches(kw, q_lower) for kw in ["chuyên cần", "điểm", "đánh giá"]):
                    resolved_target = "assessment"

                logger.info(
                    f"Session Memory Resolved: conv_id={conversation_id}, "
                    f"code={active_entity}, target={resolved_target} (source=SESSION)"
                )
                return active_entity, resolved_target, "SESSION", False
            elif has_pronoun:
                # Có đại từ nhưng phiên chưa có thực thể nào
                logger.warning(
                    f"Session Memory Unresolved: conv_id={conversation_id} contains pronoun but no active course"
                )
                return None, None, "UNRESOLVED", True

        return None, None, "NONE", False

    def update_turn(
        self,
        conversation_id: str,
        user_message: str,
        ai_message: str,
        analyzed_query: Optional[Any] = None,
        sources: Optional[List[Any]] = None,
        last_academic_entity: Optional[str] = None,
        last_entity_type: Optional[str] = None,
        last_intent: Optional[str] = None,
        last_scope: Optional[str] = None,
        last_requested_fields: Optional[List[str]] = None,
        last_completed_goal_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SessionState:
        """
        Cập nhật toàn bộ một lượt hội thoại:
        - Lưu tin nhắn người dùng và câu trả lời AI
        - Cập nhật trạng thái thực thể SessionState tất định và Discourse State
        """
        # 1. Lưu tin nhắn vào lịch sử
        self.store.append_message(conversation_id, "user", user_message)
        self.store.append_message(conversation_id, "assistant", ai_message)

        # 2. Cập nhật SessionState
        state = self.get_session_state(conversation_id)

        # Bóc tách mã môn trực tiếp từ câu hỏi người dùng
        code_match = re.search(r"\b([A-Z]{2,4}\d{4})\b", user_message, re.IGNORECASE)
        if code_match:
            new_code = code_match.group(1).upper()
            if state.active_course_code != new_code:
                logger.info(
                    f"Session Memory Entity Switching: {state.active_course_code} -> {new_code}"
                )
            state.active_course_code = new_code
            state.active_entity_type = "course"
            state.last_academic_entity = new_code
            state.last_entity_type = "course"
            state.unresolved_reference = False
        elif not state.active_course_code:
            try:
                from src.agent_core.course_resolver import get_course_resolver, ResolutionStatus
                c_res = get_course_resolver().resolve(user_message)
                if c_res.status == ResolutionStatus.RESOLVED and c_res.course_code:
                    state.active_course_code = c_res.course_code
                    state.active_course_name = c_res.canonical_name
                    state.active_entity_type = "course"
                    state.last_academic_entity = c_res.course_code
                    state.last_entity_type = "course"
                    state.unresolved_reference = False
            except Exception:
                pass

        if analyzed_query:
            # Lấy thông tin từ analyzed_query (dict hoặc model)
            aq_dict = analyzed_query.model_dump() if hasattr(analyzed_query, "model_dump") else (
                analyzed_query if isinstance(analyzed_query, dict) else {}
            )
            if aq_dict.get("course_name"):
                state.active_course_name = aq_dict["course_name"]

            targets = aq_dict.get("targets", [])
            if targets:
                # Lưu target mới nhất
                state.active_target = targets[0]

            if aq_dict.get("last_academic_entity"):
                state.last_academic_entity = aq_dict["last_academic_entity"]
            if aq_dict.get("last_intent"):
                state.last_intent = aq_dict["last_intent"]
            if aq_dict.get("last_scope"):
                state.last_scope = aq_dict["last_scope"]
            if aq_dict.get("last_requested_fields"):
                state.last_requested_fields = aq_dict["last_requested_fields"]
            if aq_dict.get("last_completed_goal_id"):
                state.last_completed_goal_id = aq_dict["last_completed_goal_id"]

        # Cập nhật Discourse State từ explicit arguments
        if last_academic_entity:
            state.last_academic_entity = last_academic_entity
            state.active_course_code = last_academic_entity
        elif state.active_course_code:
            state.last_academic_entity = state.active_course_code

        if last_entity_type:
            state.last_entity_type = last_entity_type
            state.active_entity_type = last_entity_type
        elif state.active_entity_type:
            state.last_entity_type = state.active_entity_type

        if last_intent is not None:
            state.last_intent = last_intent
        if last_scope is not None:
            state.last_scope = last_scope
        if last_requested_fields is not None:
            state.last_requested_fields = last_requested_fields
        if last_completed_goal_id is not None:
            state.last_completed_goal_id = last_completed_goal_id

        if sources:
            source_ids = []
            for s in sources:
                if isinstance(s, dict) and s.get("source"):
                    source_ids.append(str(s["source"]))
                elif hasattr(s, "source"):
                    source_ids.append(str(s.source))
                elif isinstance(s, str):
                    source_ids.append(s)
            state.last_source_ids = source_ids[:5]

        self.store.update_session_state(state)
        return state

    def clear_session(self, conversation_id: str) -> bool:
        """Xóa lịch sử và reset trạng thái của đúng phiên được yêu cầu."""
        return self.store.clear_session(conversation_id)

    def delete_session(self, conversation_id: str) -> bool:
        """Xóa hoàn toàn phiên hội thoại khỏi cơ sở dữ liệu."""
        return self.store.delete_session(conversation_id)
