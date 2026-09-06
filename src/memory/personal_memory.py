"""
Personal Memory Service: Dịch vụ điều phối bộ nhớ cá nhân dài hạn dựa trên SQLite.
Hỗ trợ quản lý sự thật cá nhân, kiểm soát quyền lực, ghi nhận nhật ký biến động (audit events),
và tiêm ngữ cảnh cá nhân hóa tối thiểu (minimal context injection).
Tuyệt đối 0 cuộc gọi LLM bên ngoài (Zero paid API calls).
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.config.settings import settings
from src.memory.store import PersonalStore
from src.memory.sqlite_store import SQLiteSessionStore
from src.memory.personal_models import (
    PersonalFact,
    MemoryWriteResult,
    SOURCE_EXPLICIT_USER,
    SOURCE_PROFILE_API,
    SOURCE_MIGRATED_LEGACY,
    KNOWN_PLACEHOLDER_DEFAULTS,
)
from src.memory.personal_policy import (
    extract_candidate_facts,
    evaluate_candidate,
    is_academic_claim,
    is_transient_or_emotional,
    is_sensitive_topic,
)

logger = logging.getLogger(__name__)


class PersonalMemoryService:
    """
    Dịch vụ quản lý bộ nhớ cá nhân hóa của người dùng (Personal Memory).
    """

    def __init__(self, store: Optional[PersonalStore] = None):
        self.store: PersonalStore = store or SQLiteSessionStore()

    def process_user_message(
        self,
        user_id: str,
        message: str,
    ) -> List[MemoryWriteResult]:
        """
        Phân tích tin nhắn người dùng, trích xuất ứng viên sự thật và áp dụng chính sách ghi nhớ an toàn.
        Đảm bảo 0 cuộc gọi LLM bên ngoài.
        """
        results: List[MemoryWriteResult] = []

        # 1. Kiểm tra nhanh nếu toàn bộ câu vi phạm chính sách cấp câu
        if is_academic_claim(message):
            logger.info("Personal Policy: Rejected entire message due to academic claims.")
            return results

        if is_transient_or_emotional(message):
            logger.info("Personal Policy: Rejected entire message due to transient/emotional tone.")
            return results

        if is_sensitive_topic(message):
            logger.info("Personal Policy: Rejected entire message due to sensitive topic.")
            return results

        # 1.1 Kiểm tra ngữ nghĩa phát ngôn (Utterance Semantics Layer)
        from src.semantics import analyze_utterance, Polarity, Modality, SubjectScope
        sem = analyze_utterance(message)
        if sem.subject_scope == SubjectScope.THIRD_PARTY:
            logger.info("Personal Policy: Rejected entire message due to third-party subject scope.")
            return results
        if sem.polarity == Polarity.NEGATED:
            logger.info("Personal Policy: Rejected entire message due to negated polarity.")
            return results
        if sem.modality in [Modality.HYPOTHETICAL, Modality.CONDITIONAL, Modality.EXPLANATORY]:
            logger.info("Personal Policy: Rejected entire message due to hypothetical/conditional/explanatory modality.")
            return results
        if sem.is_contradictory:
            logger.info("Personal Policy: Rejected entire message due to self-contradiction.")
            return results
        if sem.prohibition_detected:
            logger.info("Personal Policy: Rejected entire message due to explicit prohibition.")
            return results

        # 2. Bóc tách các ứng viên sự thật tiềm năng
        candidates = extract_candidate_facts(message)
        if not candidates:
            return results

        for fact_key, raw_val in candidates:
            is_allowed, reason, norm_val = evaluate_candidate(
                fact_key=fact_key,
                raw_val=raw_val,
                full_text=message,
                source_type=SOURCE_EXPLICIT_USER,
            )

            if not is_allowed:
                self.store.log_memory_event(
                    user_id=user_id,
                    event_type="REJECT",
                    fact_key=fact_key,
                    old_value=None,
                    new_value=raw_val,
                    source_type=SOURCE_EXPLICIT_USER,
                )
                results.append(
                    MemoryWriteResult(
                        action="REJECTED",
                        fact_key=fact_key,
                        old_value=None,
                        new_value=None,
                        source_type=SOURCE_EXPLICIT_USER,
                        reason=reason,
                    )
                )
                continue

            # Kiểm tra sự thật hiện tại
            current = self.store.get_personal_fact(user_id, fact_key)
            if current and current.value == norm_val:
                results.append(
                    MemoryWriteResult(
                        action="UNCHANGED",
                        fact_key=fact_key,
                        old_value=current.value,
                        new_value=norm_val,
                        source_type=SOURCE_EXPLICIT_USER,
                        reason="Value matches current stored memory",
                    )
                )
                continue

            action = "UPDATED" if current else "CREATED"
            self.store.upsert_personal_fact(
                user_id=user_id,
                fact_key=fact_key,
                value=norm_val,
                source_type=SOURCE_EXPLICIT_USER,
                confidence=1.0,
            )
            self.store.log_memory_event(
                user_id=user_id,
                event_type=action,
                fact_key=fact_key,
                old_value=current.value if current else None,
                new_value=norm_val,
                source_type=SOURCE_EXPLICIT_USER,
            )
            results.append(
                MemoryWriteResult(
                    action=action,
                    fact_key=fact_key,
                    old_value=current.value if current else None,
                    new_value=norm_val,
                    source_type=SOURCE_EXPLICIT_USER,
                    reason=f"Successfully {action.lower()} personal fact",
                )
            )

        return results

    def set_profile_fact(
        self,
        user_id: str,
        fact_key: str,
        value: Any,
        source_type: str = SOURCE_PROFILE_API,
    ) -> MemoryWriteResult:
        """
        Cập nhật sự thật cá nhân qua API có định kiểu (Typed Profile API).
        """
        is_allowed, reason, norm_val = evaluate_candidate(
            fact_key=fact_key,
            raw_val=value,
            full_text=f"Set {fact_key} to {value}",
            source_type=source_type,
        )

        if not is_allowed:
            self.store.log_memory_event(
                user_id=user_id,
                event_type="REJECT",
                fact_key=fact_key,
                old_value=None,
                new_value=value,
                source_type=source_type,
            )
            return MemoryWriteResult(
                action="REJECTED",
                fact_key=fact_key,
                old_value=None,
                new_value=None,
                source_type=source_type,
                reason=reason,
            )

        current = self.store.get_personal_fact(user_id, fact_key)
        if current and current.value == norm_val:
            return MemoryWriteResult(
                action="UNCHANGED",
                fact_key=fact_key,
                old_value=current.value,
                new_value=norm_val,
                source_type=source_type,
                reason="Value is identical to stored fact",
            )

        action = "UPDATED" if current else "CREATED"
        self.store.upsert_personal_fact(
            user_id=user_id,
            fact_key=fact_key,
            value=norm_val,
            source_type=source_type,
            confidence=1.0,
        )
        self.store.log_memory_event(
            user_id=user_id,
            event_type=action,
            fact_key=fact_key,
            old_value=current.value if current else None,
            new_value=norm_val,
            source_type=source_type,
        )
        return MemoryWriteResult(
            action=action,
            fact_key=fact_key,
            old_value=current.value if current else None,
            new_value=norm_val,
            source_type=source_type,
            reason=f"Fact successfully {action.lower()}",
        )

    def get_fact(self, user_id: str, fact_key: str) -> Optional[PersonalFact]:
        """Lấy một sự thật cá nhân đang hoạt động."""
        return self.store.get_personal_fact(user_id, fact_key)

    def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Lấy toàn bộ từ điển các sự thật đang hoạt động của người dùng."""
        facts = self.store.get_all_personal_facts(user_id, status="ACTIVE")
        return {f.fact_key: f.value for f in facts}

    def delete_fact(self, user_id: str, fact_key: str) -> bool:
        """Xóa một sự thật cá nhân cụ thể của người dùng."""
        current = self.store.get_personal_fact(user_id, fact_key)
        if not current:
            return False

        deleted = self.store.delete_personal_fact(user_id, fact_key)
        if deleted:
            self.store.log_memory_event(
                user_id=user_id,
                event_type="DELETE",
                fact_key=fact_key,
                old_value=current.value,
                new_value=None,
                source_type="USER_REQUEST",
            )
        return deleted

    def clear_memory(self, user_id: str) -> int:
        """Xóa toàn bộ sự thật cá nhân của người dùng."""
        count = self.store.clear_personal_facts(user_id)
        if count > 0:
            self.store.log_memory_event(
                user_id=user_id,
                event_type="DELETE_ALL",
                fact_key="*",
                old_value=f"count={count}",
                new_value=None,
                source_type="USER_REQUEST",
            )
        return count

    def get_relevant_profile_context(
        self,
        query: str,
        category: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Tiêm ngữ cảnh cá nhân hóa tối thiểu (Minimal Context Injection).
        Chỉ cung cấp những thông tin thật sự cần thiết cho từng loại câu hỏi,
        không bao giờ đổ toàn bộ hồ sơ hoặc dữ liệu nhạy cảm vào prompt.
        """
        active_facts = self.get_user_profile(user_id)
        if not active_facts:
            return {}

        relevant: Dict[str, Any] = {}
        q_lower = query.lower()

        # 1. Tùy chọn phong cách phản hồi và ngôn ngữ (hầu như áp dụng chung nếu người dùng có khai báo)
        if "response_style" in active_facts:
            relevant["response_style"] = active_facts["response_style"]
        if "preferred_language" in active_facts:
            relevant["preferred_language"] = active_facts["preferred_language"]
        if "preferred_name" in active_facts:
            relevant["preferred_name"] = active_facts["preferred_name"]

        # 2. Với câu hỏi tổng quan CS / GENERAL_LLM:
        if category == "GENERAL_LLM":
            # Tuyệt đối không tiêm email, cohort, major vào câu hỏi khái niệm thuần túy
            return relevant

        # 3. Với câu hỏi liên quan đến định hướng, lộ trình, học kỳ tới, khung chương trình:
        is_planning_query = any(kw in q_lower for kw in [
            "kỳ tới", "kỳ sau", "học kỳ tới", "nên học gì", "lộ trình",
            "chương trình", "định hướng", "tốt nghiệp", "khung", "kế hoạch"
        ])
        if is_planning_query:
            if "major" in active_facts:
                relevant["major"] = active_facts["major"]
            if "cohort" in active_facts:
                relevant["cohort"] = active_facts["cohort"]
            if "current_semester" in active_facts:
                relevant["current_semester"] = active_facts["current_semester"]
            if "learning_goal" in active_facts:
                relevant["learning_goal"] = active_facts["learning_goal"]

        return relevant

    def migrate_legacy_profile(
        self,
        legacy_profile_path: Optional[Path] = None,
        user_id: str = "local-user",
    ) -> Dict[str, Any]:
        """
        Di chuyển an toàn từ file JSON legacy (`runtime/student_profile.json`).
        Loại bỏ tuyệt đối các giá trị placeholder mặc định giả định.
        """
        path = legacy_profile_path or (settings.RUNTIME_DIR / "student_profile.json")
        summary: Dict[str, List[str]] = {
            "migrated": [],
            "ignored_placeholders": [],
            "rejected": [],
        }

        if not path.exists():
            return summary

        try:
            with open(path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
        except Exception as e:
            logger.error(f"Legacy Migration: Loi doc file {path}: {e}")
            return summary

        # Mapping các khóa legacy sang khóa chuẩn mới
        key_map = {
            "name": "preferred_name",
            "major": "major",
            "cohort": "cohort",
            "style": "response_style",
            "email": "own_email",
        }

        for old_k, old_v in data.items():
            if old_v is None or not str(old_v).strip():
                continue

            # Kiểm tra nếu giá trị khớp đúng placeholder mặc định giả định
            if old_k in KNOWN_PLACEHOLDER_DEFAULTS and str(old_v).strip() == KNOWN_PLACEHOLDER_DEFAULTS[old_k]:
                summary["ignored_placeholders"].append(f"{old_k}={old_v}")
                logger.info(f"Legacy Migration: Ignored placeholder default '{old_k}={old_v}'")
                continue

            target_key = key_map.get(old_k, old_k)
            is_allowed, reason, norm_val = evaluate_candidate(
                fact_key=target_key,
                raw_val=old_v,
                full_text=f"Legacy {target_key} {old_v}",
                source_type=SOURCE_MIGRATED_LEGACY,
            )

            if is_allowed:
                self.store.upsert_personal_fact(
                    user_id=user_id,
                    fact_key=target_key,
                    value=norm_val,
                    source_type=SOURCE_MIGRATED_LEGACY,
                    confidence=0.85,
                )
                self.store.log_memory_event(
                    user_id=user_id,
                    event_type="MIGRATE",
                    fact_key=target_key,
                    old_value=None,
                    new_value=norm_val,
                    source_type=SOURCE_MIGRATED_LEGACY,
                )
                summary["migrated"].append(f"{target_key}={norm_val}")
                logger.info(f"Legacy Migration: Successfully migrated '{target_key}={norm_val}'")
            else:
                summary["rejected"].append(f"{target_key}={old_v} (reason: {reason})")
                logger.warning(f"Legacy Migration: Rejected '{target_key}={old_v}': {reason}")

        return summary
