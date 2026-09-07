"""
Action Authorization Gate Policy.
Enforces non-negotiable safety rules before executing any side-effect tool action.
Guarantees: Router classification does NOT imply action execution.
Strictly local: 0 external LLM calls.
"""
import re
from typing import Dict, Any, Optional

from src.semantics.schemas import (
    Polarity,
    Modality,
    ActionOperation,
    UtteranceSemantics,
    ActionAuthorizationDecision,
)


class ActionAuthorizationGate:
    """Cổng thẩm quyền và an toàn thực thi hành động công cụ."""

    @staticmethod
    def authorize(
        semantics: UtteranceSemantics,
        requested_tool: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ActionAuthorizationDecision:
        """
        Đánh giá tính an toàn và thẩm quyền thực thi hành động.
        """
        raw_text = semantics.raw_text
        target_op = semantics.target_operation

        # Nếu router đề xuất requested_tool
        if requested_tool == "SEND_EMAIL":
            if ActionOperation.COMPOSE_EMAIL in semantics.action_requests:
                target_op = ActionOperation.COMPOSE_EMAIL
            elif ActionOperation.SEND_EMAIL in semantics.action_prohibitions or semantics.polarity == Polarity.NEGATED:
                target_op = ActionOperation.NO_ACTION
            elif not target_op or target_op == ActionOperation.NO_ACTION:
                if ActionOperation.SEND_EMAIL in semantics.action_requests:
                    target_op = ActionOperation.SEND_EMAIL
        elif requested_tool == "SET_REMINDER":
            if ActionOperation.SET_REMINDER in semantics.action_prohibitions or semantics.polarity == Polarity.NEGATED:
                target_op = ActionOperation.NO_ACTION
            elif not target_op or target_op == ActionOperation.NO_ACTION:
                if ActionOperation.SET_REMINDER in semantics.action_requests:
                    target_op = ActionOperation.SET_REMINDER

        # 1. KIỂM TRA MÂU THUẪN (Contradictory Instructions)
        if semantics.is_contradictory:
            return ActionAuthorizationDecision(
                operation=ActionOperation.CLARIFY,
                authorized=False,
                side_effect=False,
                reason_code="CONTRADICTORY_ACTION",
                requires_clarification=True,
                clarification_message=(
                    "Yêu cầu của bạn có các chỉ dẫn trái ngược nhau (vừa yêu cầu vừa hủy hoặc đổi ý). "
                    "Vui lòng xác nhận rõ ràng bạn có muốn thực hiện hành động này không?"
                ),
                safe_response=(
                    "⚠️ Yêu cầu của bạn có các chỉ dẫn trái ngược nhau (vừa yêu cầu vừa hủy hoặc đổi ý). "
                    "Vui lòng xác nhận rõ ràng bạn có muốn thực hiện hành động này không?"
                ),
            )

        # 2. KIỂM TRA PHƯƠNG THỨC GIẢI THÍCH KHÁI NIỆM (Explanatory / Informational)
        if semantics.modality == Modality.EXPLANATORY:
            safe_msg = "Chức năng này hỗ trợ sinh viên trong quá trình học tập."
            if "email" in raw_text.lower():
                safe_msg = (
                    "📧 **Tính năng Email**: Cho phép gửi email thông báo học vụ tới giảng viên hoặc phòng ban "
                    "thông qua địa chỉ email trường Đại Nam (@dainam.edu.vn)."
                )
            elif "nhắc" in raw_text.lower() or "reminder" in raw_text.lower():
                safe_msg = (
                    "⏰ **Tính năng Nhắc nhở**: Cho phép bạn lên lịch hẹn tự động để nhắc ôn thi, "
                    "hạn nộp bài tập hoặc sự kiện quan trọng trong kỳ học."
                )
            return ActionAuthorizationDecision(
                operation=ActionOperation.NO_ACTION,
                authorized=False,
                side_effect=False,
                reason_code="EXPLANATORY_ONLY",
                requires_clarification=False,
                safe_response=safe_msg,
            )

        # 3. KIỂM TRA GIẢ ĐỊNH / PHẢN THỰC TẾ (Hypothetical / Conditional)
        if semantics.modality in [Modality.HYPOTHETICAL, Modality.CONDITIONAL]:
            return ActionAuthorizationDecision(
                operation=ActionOperation.NO_ACTION,
                authorized=False,
                side_effect=False,
                reason_code="HYPOTHETICAL_OR_CONDITIONAL_ACTION",
                requires_clarification=False,
                safe_response=(
                    "ℹ️ Đây là câu hỏi giả định hoặc có điều kiện chưa xác nhận. "
                    "Hệ thống ghi nhận nhưng không kích hoạt hành động thực tế nào."
                ),
            )

        # 4. XỬ LÝ THAO TÁC SOẠN EMAIL (DRAFT - AN TOÀN, KHÔNG PHẢI SIDE EFFECT)
        if target_op == ActionOperation.COMPOSE_EMAIL:
            return ActionAuthorizationDecision(
                operation=ActionOperation.COMPOSE_EMAIL,
                authorized=True,
                side_effect=False,
                reason_code="AUTHORIZED_COMPOSE_DRAFT",
                requires_clarification=False,
                safe_response=None,
            )

        # 5. XỬ LÝ PHỦ ĐỊNH GỬI EMAIL (SEND_EMAIL PROHIBITED)
        if (
            ActionOperation.SEND_EMAIL in semantics.action_prohibitions
            or (target_op == ActionOperation.SEND_EMAIL and semantics.polarity == Polarity.NEGATED)
            or (requested_tool == "SEND_EMAIL" and (semantics.polarity == Polarity.NEGATED or semantics.prohibition_detected))
        ):
            return ActionAuthorizationDecision(
                operation=ActionOperation.NO_ACTION,
                authorized=False,
                side_effect=False,
                reason_code="NEGATED_ACTION",
                requires_clarification=False,
                safe_response="✅ Đã ghi nhận yêu cầu KHÔNG gửi email. Hệ thống sẽ không gửi bất kỳ email nào.",
            )

        # 6. XỬ LÝ PHỦ ĐỊNH NHẮC NHỞ (SET_REMINDER PROHIBITED)
        if (
            ActionOperation.SET_REMINDER in semantics.action_prohibitions
            or (target_op == ActionOperation.SET_REMINDER and semantics.polarity == Polarity.NEGATED)
            or (requested_tool == "SET_REMINDER" and (semantics.polarity == Polarity.NEGATED or semantics.prohibition_detected))
        ):
            return ActionAuthorizationDecision(
                operation=ActionOperation.NO_ACTION,
                authorized=False,
                side_effect=False,
                reason_code="NEGATED_ACTION",
                requires_clarification=False,
                safe_response="✅ Đã ghi nhận yêu cầu KHÔNG đặt lịch nhắc. Hệ thống sẽ không kích hoạt lịch nhắc này.",
            )

        # 7. XỬ LÝ GỬI EMAIL THỰC TẾ (SEND_EMAIL SIDE EFFECT)
        if target_op == ActionOperation.SEND_EMAIL and semantics.polarity == Polarity.AFFIRMATIVE:
            # Kiểm tra xem có email người nhận hợp lệ không
            explicit_emails = list(dict.fromkeys(re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", raw_text)))
            if len(explicit_emails) > 1:
                return ActionAuthorizationDecision(
                    operation=ActionOperation.CLARIFY,
                    authorized=False,
                    side_effect=False,
                    reason_code="MULTIPLE_RECIPIENTS_FOUND",
                    requires_clarification=True,
                    clarification_message=f"Hệ thống tìm thấy nhiều địa chỉ email khả dụng ({', '.join(explicit_emails)}). Bạn muốn gửi email tới địa chỉ nào?",
                    safe_response=f"Hệ thống tìm thấy nhiều địa chỉ email khả dụng ({', '.join(explicit_emails)}). Bạn muốn gửi email tới địa chỉ nào?",
                )

            recipient = None
            if len(explicit_emails) == 1:
                recipient = explicit_emails[0]
            elif context and context.get("available_recipients"):
                rec_list = context["available_recipients"]
                if len(rec_list) == 1:
                    recipient = rec_list[0]
                elif len(rec_list) > 1:
                    return ActionAuthorizationDecision(
                        operation=ActionOperation.CLARIFY,
                        authorized=False,
                        side_effect=False,
                        reason_code="MULTIPLE_RECIPIENTS_FOUND",
                        requires_clarification=True,
                        clarification_message=f"Hệ thống tìm thấy nhiều địa chỉ email khả dụng ({', '.join(rec_list)}). Bạn muốn gửi email tới địa chỉ nào?",
                        safe_response=f"Hệ thống tìm thấy nhiều địa chỉ email khả dụng ({', '.join(rec_list)}). Bạn muốn gửi email tới địa chỉ nào?",
                    )

            if not recipient:
                return ActionAuthorizationDecision(
                    operation=ActionOperation.CLARIFY,
                    authorized=False,
                    side_effect=False,
                    reason_code="UNRESOLVED_RECIPIENT_EMAIL",
                    requires_clarification=True,
                    clarification_message="Bạn muốn gửi email tới địa chỉ nào? Vui lòng cung cấp địa chỉ email người nhận hợp lệ.",
                    safe_response="Bạn muốn gửi email tới địa chỉ nào? Vui lòng cung cấp địa chỉ email người nhận hợp lệ.",
                )

            return ActionAuthorizationDecision(
                operation=ActionOperation.SEND_EMAIL,
                authorized=True,
                side_effect=True,
                reason_code="AUTHORIZED_SEND_EMAIL",
                requires_clarification=False,
                metadata={"recipient": recipient},
            )

        # 8. XỬ LÝ ĐẶT LỊCH NHẮC THỰC TẾ (SET_REMINDER SIDE EFFECT)
        if target_op == ActionOperation.SET_REMINDER and semantics.polarity == Polarity.AFFIRMATIVE:
            return ActionAuthorizationDecision(
                operation=ActionOperation.SET_REMINDER,
                authorized=True,
                side_effect=True,
                reason_code="AUTHORIZED_SET_REMINDER",
                requires_clarification=False,
            )

        # 9. MẶC ĐỊNH TỪ CHỐI AN TOÀN (DEFAULT SAFE DENIAL)
        return ActionAuthorizationDecision(
            operation=ActionOperation.NO_ACTION,
            authorized=False,
            side_effect=False,
            reason_code="NO_AUTHORIZED_ACTION",
            requires_clarification=False,
            safe_response=None,
        )


def authorize_tool_action(
    semantics: UtteranceSemantics,
    requested_tool: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> ActionAuthorizationDecision:
    """Hàm tiện ích nhanh để thẩm tra hành động qua Action Authorization Gate."""
    return ActionAuthorizationGate.authorize(
        semantics=semantics,
        requested_tool=requested_tool,
        context=context,
    )
