"""
Utterance Semantics Analyzer.
Extracts linguistic polarity, modality, subject scope, contradiction,
and action operations from Vietnamese and bilingual user utterances.
Strictly local: 0 external LLM calls.
"""
import re
from typing import List, Optional, Tuple

from src.semantics.schemas import (
    Polarity,
    Modality,
    SubjectScope,
    ActionOperation,
    UtteranceSemantics,
)
from src.semantics.normalizer import (
    normalize_for_semantics,
)


class UtteranceSemanticsAnalyzer:
    """Bộ phân tích ngữ nghĩa phát ngôn cục bộ độc lập."""

    def __init__(self):
        # 1. Các mẫu từ chỉ định phủ định (Negation Markers)
        self.negation_word_patterns = [
            r"\bkhông\s+phải\b",
            r"\bkhông\s+cần\b",
            r"\bkhông\s+muốn\b",
            r"\bđừng\s+có\b",
            r"\bthôi\s+không\b",
            r"\bchẳng\s+phải\b",
            r"\bđừng\s+bao\s+giờ\b",
            r"\bkhông\s+được\b",
            r"\b(đừng|chớ|thôi|ngưng|hủy|bỏ|chẳng|chưa|không|miễn|dừng|tắt|ngừng)\b",
        ]

        # 2. Các mẫu chỉ định phương thức giả định (Hypothetical Modality)
        self.hypothetical_patterns = [
            r"\b(giả\s+sử|giả\s+định|ví\s+dụ|thử\s+tưởng\s+tượng|coi\s+như|thử\s+nghĩ\s+xem)\b",
            r"^\s*nếu\b",
            r"\b(nếu\s+như|nếu\s+tôi|nếu\s+mình|nếu\s+em|nếu\s+mai|nếu\s+trường|nếu\s+muốn|nếu\s+cần|nếu\s+gửi|nếu\s+đặt|nếu\s+bảo)\b",
            r"\bnếu\s+.*(thì|sao|được|làm\s+sao|mất\s+bao\s+lâu|nhận\s+được|nhớ|lưu)\b",
            r"\b(suppose|what\s+if|assuming)\b",
            r"\b(liệu\s+có\s+thể|liệu\s+tôi|liệu\s+bạn)\b",
        ]

        # 3. Các mẫu chỉ định điều kiện chưa xác định (Conditional Modality)
        self.conditional_patterns = [
            r"\b(khi\s+nào|hễ|chừng\s+nào|đợi|chờ|bao\s+giờ)\s+.*\s+(thì|mới|hãy)\b",
            r"\b(khi\s+nào\s+.*\s+thì)\b",
            r"\b(hễ\s+.*\s+thì)\b",
            r"\b(chừng\s+nào\s+.*\s+mới)\b",
            r"\b(đợi\s+.*\s+hãy)\b",
            r"\b(đợi\s+.*\s+mới)\b",
            r"\b(chờ\s+.*\s+thì\s+mới)\b",
            r"\b(chờ\s+.*\s+mới)\b",
        ]

        # 4. Các mẫu giải thích khái niệm / thông tin công cụ (Explanatory Modality)
        self.explanatory_patterns = [
            r"\b(email|thư\s+điện\s+tử|lịch\s+nhắc|nhắc\s+nhở|reminder|scheduler|smtp|hệ\s+thống).*\b(là\s+gì|như\s+thế\s+nào|ra\s+sao|để\s+làm\s+gì|có\s+vai\s+trò\s+gì|hoạt\s+động\s+như\s+thế\s+nào|hoạt\s+động\s+ra\s+sao)\b",
            r"\b(cách|hướng\s+dẫn|làm\s+sao|làm\s+thế\s+nào|làm\s+cách\s+nào)\b.*(gửi|đặt|tạo|lên\s+lịch|sử\s+dụng|hủy|xem|biết).*(email|thư|nhắc|lịch|reminder)\b",
            r"\b(giao\s+thức|tính\s+năng|chức\s+năng|cơ\s+chế|hệ\s+thống|thư\s+viện)\b.*(email|thư|nhắc|reminder|scheduler|smtp)",
            r"\b(giải\s+thích|tìm\s+hiểu|thông\s+tin\s+về)\s+.*(tính\s+năng|chức\s+năng|email|lịch\s+nhắc|nhắc\s+nhở|reminder)\b",
            r"\b(ai\s+có\s+quyền|ai\s+được\s+phép)\s+(gửi|đặt|tạo|nhắc)\b",
            r"\b(khi\s+nào|lúc\s+nào)\s+.*(bot\s+sẽ\s+gửi|gửi\s+email|nhắc)\b",
            r"\b(địa\s+chỉ\s+email|email\s+của)\s+.*\s+(ở\s+đâu|lấy\s+ở\s+đâu)\b",
            r"\b(có\s+những\s+hình\s+thức|có\s+mấy\s+hình\s+thức|có\s+mấy\s+loại)\b.*(nhắc|nhắc\s+nhở|email)\b",
            r"\b(dùng\s+thư\s+viện\s+gì|dùng\s+gì|dùng\s+công\s+nghệ\s+gì)\b.*(lên\s+lịch|nhắc|scheduler|email)\b",
            r"\b(có\s+tự\s+động\s+.*không|có\s+mất\s+phí\s+không|có\s+mất\s+tiền\s+không)\b",
            r"\b(giới\s+hạn\s+dung\s+lượng|định\s+dạng\s+thời\s+gian|cơ\s+chế\s+bảo\s+mật|bảo\s+mật)\b.*(email|nhắc|lịch)\b",
            r"\b(làm\s+sao|làm\s+thế\s+nào|cách\s+nào)\s+để\s+(biết|kiểm\s+tra)\s+email\s+.*gửi\s+thành\s+công\b",
            r"\blịch\s+nhắc\s+có\s+tự\s+động\b",
            r"\bcơ\s+chế\s+bảo\s+mật\s+khi\s+gửi\s+email\b",
        ]

        # 5. Các mẫu đối tượng chủ thể bên thứ ba (Third-Party Scope)
        self.third_party_patterns = [
            r"\b(bạn|anh|chị|em|thầy|cô|bố|mẹ|người\s+khác|thằng\s+bạn|bạn\s+cùng\s+phòng|bạn\s+cùng\s+bàn|bạn\s+cùng\s+lớp|bạn\s+thân|anh\s+trai|chị\s+gái|em\s+trai|em\s+gái|anh\s+họ)\s+(tôi|mình|em|của\s+tôi)\b",
            r"\b(bạn\s+thân|bạn\s+cùng\s+bàn|bạn\s+cùng\s+phòng|bạn\s+cùng\s+lớp|anh\s+trai|chị\s+gái|em\s+trai|em\s+gái|anh\s+họ)\b",
            r"\b(sinh\s+viên\s+trong\s+lớp|bạn\s+trong\s+lớp|sinh\s+viên\s+khác|người\s+khác)\b",
            r"\b(bạn\s+ấy|anh\s+ấy|chị\s+ấy|cô\s+ấy|thầy\s+ấy|họ|ai\s+đó|người\s+ta|nhóm\s+bạn)\b",
            r"\b(anh|chị|thầy|cô)\s+([A-ZÀ-Ỹa-zà-ỹ]+)\s+(học|dạy|là|tên|muốn|thích)\b",
        ]

        # 6. Các mẫu mâu thuẫn / thay đổi ý định (Contradiction Markers)
        self.explicit_contradiction_markers = [
            r"\bà\s+không\b",
            r"\bà\s+nhầm\b",
            r"\bkhoan\s+đã\b",
            r"\bkhoan\b",
            r"\bđổi\s+ý\b",
            r"\bnhưng\s+thôi\b",
            r"\bmà\s+thôi\b",
            r"\b(nhưng\s+thật\s+ra|nhưng\s+thực\s+tế|nhưng\s+thực\s+ra|thật\s+ra\s+là|thực\s+ra\s+là)\b",
            r"\b(gửi\s*\.\.\.\s*không|nhắc\s*\.\.\.\s*thôi)\b",
            r"\b(khoan\s+không)\b",
            r"\b(thử\s+.*nhưng\s+đừng)\b",
            r"\b(nhưng\s+mà\s+thôi)\b",
            r"\b(đừng\s+gửi\s*[\.,]\s*à\s+gửi)\b",
            r"\b(thôi\s+không\s+cần|thôi\s+khỏi|thôi\s+bỏ\s+đi)\b",
        ]

    def analyze(self, text: str) -> UtteranceSemantics:
        """Phân tích toàn diện một phát ngôn và trích xuất cấu trúc tín hiệu ngữ nghĩa."""
        raw_text = text or ""
        norm_text = normalize_for_semantics(raw_text)

        # 1. Phân tích Modality (Phương thức phát ngôn)
        modality = self._detect_modality(norm_text, raw_text)

        # 2. Phân tích Subject Scope (Chủ thể phát ngôn)
        subject_scope = self._detect_subject_scope(norm_text)

        # 3. Phân tích Thao tác Công cụ & Phủ định (Actions & Negation & Contradiction)
        action_requests, action_prohibitions, polarity, is_contradictory = self._detect_actions_and_polarity(
            norm_text, modality
        )

        # 4. Xác định thao tác mục tiêu cuối cùng (Target Operation)
        target_op = self._resolve_target_operation(
            action_requests=action_requests,
            action_prohibitions=action_prohibitions,
            is_contradictory=is_contradictory,
            modality=modality,
            polarity=polarity,
        )

        has_explicit_prohibition = len(action_prohibitions) > 0 or bool(re.search(r"\b(đừng|chớ|cấm|không\s+được|không\s+cần\s+nhớ|đừng\s+nhớ|thôi\s+không)\b", norm_text))

        return UtteranceSemantics(
            raw_text=raw_text,
            normalized_text=norm_text,
            polarity=polarity,
            modality=modality,
            subject_scope=subject_scope,
            is_contradictory=is_contradictory,
            prohibition_detected=has_explicit_prohibition,
            action_requests=action_requests,
            action_prohibitions=action_prohibitions,
            target_operation=target_op,
            details={
                "has_action_request": len(action_requests) > 0,
                "has_action_prohibition": len(action_prohibitions) > 0,
            },
        )

    def _detect_modality(self, norm_text: str, raw_text: str) -> Modality:
        # Kiểm tra Explanatory trước (Hỏi cách thức, định nghĩa)
        for p in self.explanatory_patterns:
            if re.search(p, norm_text):
                return Modality.EXPLANATORY

        # Kiểm tra Hypothetical (Giả định, phản thực tế)
        for p in self.hypothetical_patterns:
            if re.search(p, norm_text):
                return Modality.HYPOTHETICAL

        # Kiểm tra Conditional (Điều kiện chưa thỏa mãn)
        for p in self.conditional_patterns:
            if re.search(p, norm_text):
                return Modality.CONDITIONAL

        # Kiểm tra Question (Câu hỏi thông thường)
        if "?" in raw_text or any(w in norm_text for w in ["bao nhiêu", "mấy", "ở đâu", "ai là", "thế nào", "được không"]):
            return Modality.QUESTION

        # Mặc định: Phát ngôn trực tiếp / Mệnh lệnh
        return Modality.DIRECT

    def _detect_subject_scope(self, norm_text: str) -> SubjectScope:
        for p in self.third_party_patterns:
            if re.search(p, norm_text):
                return SubjectScope.THIRD_PARTY

        # Nhận diện tự thân (Self)
        self_markers = [r"\b(tôi|mình|em|tớ|bản\s+thân)\b"]
        for p in self_markers:
            if re.search(p, norm_text):
                return SubjectScope.SELF

        return SubjectScope.UNKNOWN

    def _detect_actions_and_polarity(
        self, norm_text: str, modality: Modality
    ) -> Tuple[List[ActionOperation], List[ActionOperation], Polarity, bool]:
        action_requests: List[ActionOperation] = []
        action_prohibitions: List[ActionOperation] = []
        is_contradictory = False

        # 1. Phát hiện SOẠN EMAIL DRAFT (DRAFT ONLY - An toàn, không có side effect)
        draft_only_patterns = [
            r"\b(chỉ\s+soạn|soạn\s+thôi|chỉ\s+viết|viết\s+thôi|lưu\s+nháp|để\s+nháp|tự\s+gửi|tự\s+copy|xem\s+thử|chỉ\s+xem\s+thử)\b",
            r"\b(bản\s+thảo|dự\s+thảo|bản\s+nháp|nháp|draft|template|mẫu\s+(thư|email|mail)|(thư|email|mail)\s+mẫu|tạo\s+mẫu|dàn\s+ý|khung)\b",
            r"\bwithout\s+sending\b",
            r"\b(soạn|viết|tạo)\s+.*(không|đừng|chưa|chớ)\s+(bấm\s+|nhấn\s+|có\s+)?(gửi|send)\b",
            r"\b(thử\s+viết|viết\s+thử|soạn\s+thử|thử\s+soạn)\b",
        ]
        is_compose = any(re.search(p, norm_text) for p in draft_only_patterns)

        # Kiểm tra các mẫu mâu thuẫn biểu kiến
        for p in self.explicit_contradiction_markers:
            if re.search(p, norm_text):
                is_contradictory = True
                break

        # 2. Phân tích CẤM GỬI EMAIL vs YÊU CẦU GỬI EMAIL bằng Masking
        masked_text = norm_text

        send_prohibit_patterns = [
            r"\b(đừng|không|thôi|ngưng|hủy|bỏ|chớ|miễn|dừng|ngừng)\s+(cần\s+)?(bấm\s+|nhấn\s+|click\s+|ấn\s+)?(gửi|send)\s*(?:email|mail|thư)?(?:\s+(?:nữa|nhé|nha|đâu|đi|ngay))*\b",
            r"\bwithout\s+sending\b",
            r"\b(do\s+not|don't)\s+send\b",
            r"\b(dừng|ngừng|tắt)\s+(việc\s+)?(gửi|send)\s*(?:email|mail|thư)?\b",
            r"\b(dừng|ngừng)\s+.*(thư\s+điện\s+tử|email|mail)\b",
            r"\bkhông\s+muốn\s+gửi\s*(?:email|mail|thư)?\b",
            r"\bđừng\s+bao\s+giờ\s+gửi\b",
            r"\bkhông\s+gửi\s*(?:email|mail|thư)?\s*(?:nhé|nữa|nha|đâu)?\b",
            r"\bhủy\s+(?:việc\s+)?gửi\s*(?:email|mail|thư)?\b",
            r"\bthử\s+tính\s+năng\s+gửi\s+email\s+.*nhưng\s+đừng\s+gửi\b",
        ]
        has_send_prohibition = False
        for p in send_prohibit_patterns:
            if re.search(p, masked_text):
                has_send_prohibition = True
                masked_text = re.sub(p, " __PROHIBIT_SEND__ ", masked_text)

        if has_send_prohibition:
            action_prohibitions.append(ActionOperation.SEND_EMAIL)

        # Kiểm tra xem trong phần còn lại có yêu cầu gửi khẳng định không
        send_positive_patterns = [
            r"\b(gửi|send)\s+(?:email|mail|thư)\b",
            r"\b(email|mail|thư)\s+(?:gửi|tới|cho|đến)\b",
            r"\b(soạn|viết|soạn thảo|gửi|send)\s+(?:giúp\s+|hộ\s+)?(?:tôi\s+)?(?:một\s+)?(?:bản\s+)?(?:email|mail|thư)(?:\s+điện\s+tử)?\b",
            r"\b(gửi|send)\s+.*@.*\b",
            r"\b(bắn|chuyển)\s+(?:email|mail)\b",
        ]
        has_positive_send = any(re.search(p, masked_text) for p in send_positive_patterns)

        # Nếu có cả lệnh gửi và lệnh cấm gửi (và không phải dạng soạn nhưng đừng gửi) -> MÂU THUẪN
        if has_send_prohibition and has_positive_send and not is_compose:
            is_contradictory = True

        # 3. Phân tích CẤM NHẮC NHỞ vs YÊU CẦU NHẮC NHỞ bằng Masking
        remind_prohibit_patterns = [
            r"\b(đừng|không|thôi|ngưng|hủy|bỏ|chớ|miễn|dừng|ngừng)\s+(cần\s+)?(nhắc|hẹn|đặt\s+lịch|lên\s+lịch|báo\s+thức|tạo\s+sự\s+kiện|đặt\s+lịch\s+nhắc|lên\s+lịch\s+nhắc)(?:\s+(?:nhắc|lịch|nhé|nữa|nha|đâu|tôi|bài\s+tập))*\b",
            r"\b(tắt|hủy|dừng|ngừng)\s+(mọi|toàn\s+bộ|các)?\s*(chức\s+năng\s+nhắc|lịch\s+nhắc|báo\s+thức|nhắc\s+nhở|thông\s+báo\s+nhắc\s+nhở|thông\s+báo)\b",
            r"\bdừng\s+lịch\s+nhắc\b",
            r"\bkhông\s+cần\s+nhắc(?:\s+tôi)?(?:\s+đâu)?\b",
            r"\bđừng\s+nhắc\b",
            r"\bkhông\s+nhắc\b",
            r"\bthôi\s+không\s+nhắc\b",
        ]
        has_remind_prohibition = False
        for p in remind_prohibit_patterns:
            if re.search(p, masked_text):
                has_remind_prohibition = True
                masked_text = re.sub(p, " __PROHIBIT_REMIND__ ", masked_text)

        if has_remind_prohibition:
            action_prohibitions.append(ActionOperation.SET_REMINDER)

        # Kiểm tra xem trong phần còn lại có yêu cầu nhắc nhở khẳng định không
        remind_positive_patterns = [
            r"\b(nhắc|nhắc\s+nhở|đặt\s+lịch|lên\s+lịch|hẹn\s+giờ|báo\s+thức|tạo\s+reminder)\b",
        ]
        has_positive_remind = any(re.search(p, masked_text) for p in remind_positive_patterns)

        if has_remind_prohibition and has_positive_remind:
            is_contradictory = True

        # Ghi nhận Action Requests
        if is_compose:
            action_requests.append(ActionOperation.COMPOSE_EMAIL)
        elif has_positive_send and not has_send_prohibition:
            action_requests.append(ActionOperation.SEND_EMAIL)

        if has_positive_remind and not has_remind_prohibition:
            action_requests.append(ActionOperation.SET_REMINDER)

        # 4. Xác định Polarity tổng thể
        has_general_negation = any(re.search(p, norm_text) for p in self.negation_word_patterns)

        if is_contradictory:
            polarity = Polarity.MIXED
        elif is_compose and has_send_prohibition:
            # "Soạn email nhưng đừng gửi" -> Soạn là +, gửi là - -> MIXED
            polarity = Polarity.MIXED
        elif has_send_prohibition or has_remind_prohibition:
            polarity = Polarity.NEGATED
        elif has_general_negation:
            polarity = Polarity.NEGATED
        else:
            polarity = Polarity.AFFIRMATIVE

        return action_requests, action_prohibitions, polarity, is_contradictory

    def _resolve_target_operation(
        self,
        action_requests: List[ActionOperation],
        action_prohibitions: List[ActionOperation],
        is_contradictory: bool,
        modality: Modality,
        polarity: Polarity,
    ) -> ActionOperation:
        # Nếu mâu thuẫn -> CLARIFY
        if is_contradictory:
            return ActionOperation.CLARIFY

        # Nếu là câu hỏi khái niệm / giả định / điều kiện -> Không thực hiện
        if modality in [Modality.EXPLANATORY, Modality.HYPOTHETICAL, Modality.CONDITIONAL]:
            return ActionOperation.NO_ACTION

        # Soạn thảo bản nháp (an toàn, ưu tiên cao hơn cấm gửi)
        if ActionOperation.COMPOSE_EMAIL in action_requests:
            return ActionOperation.COMPOSE_EMAIL

        # Nếu bị cấm gửi email
        if ActionOperation.SEND_EMAIL in action_prohibitions:
            return ActionOperation.NO_ACTION

        # Nếu bị cấm nhắc nhở
        if ActionOperation.SET_REMINDER in action_prohibitions:
            return ActionOperation.NO_ACTION

        # Nếu có yêu cầu gửi email hợp lệ
        if ActionOperation.SEND_EMAIL in action_requests:
            return ActionOperation.SEND_EMAIL

        # Nếu có yêu cầu nhắc nhở hợp lệ
        if ActionOperation.SET_REMINDER in action_requests:
            return ActionOperation.SET_REMINDER

        return ActionOperation.NO_ACTION


# Singleton Analyzer Instance
_analyzer_instance: Optional[UtteranceSemanticsAnalyzer] = None


def get_semantics_analyzer() -> UtteranceSemanticsAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = UtteranceSemanticsAnalyzer()
    return _analyzer_instance


def analyze_utterance(text: str) -> UtteranceSemantics:
    """Hàm tiện ích nhanh để phân tích ngữ nghĩa phát ngôn."""
    return get_semantics_analyzer().analyze(text)
