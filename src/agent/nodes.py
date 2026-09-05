"""
LangGraph Nodes cho AI Academic Advisor Agent.
Xử lý toàn bộ các bước: Cache -> Analysis -> Router -> RAG/Direct/Tool -> Validation -> Save.
"""
import re
import json
import uuid
import datetime
import logging
from typing import Dict, Any, Optional

from src.config.settings import settings
from src.llm.client import invoke_llm
from src.cache.exact_cache import get_exact_cache
from src.memory.memory_manager import get_memory_manager
from src.rag.query_analyzer import analyze_query, AnalyzedQuery
from src.rag.hybrid_retriever import retrieve_candidates
from src.rag.reranker import rerank_documents
from src.rag.context_builder import build_context
from src.router import get_router_service
from src.prompts.answer_prompt import GROUNDED_ANSWER_PROMPT, GENERAL_ANSWER_PROMPT
from src.prompts.validation_prompt import VALIDATION_PROMPT
from src.tools.email_sender import EmailSender
from src.scheduler.reminder_scheduler import schedule_reminder

logger = logging.getLogger(__name__)

_email_sender = EmailSender()


# ==============================================================================
# 1. CACHE NODE
# ==============================================================================
def cache_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("question", "").strip()
    cache = get_exact_cache()
    cached_entry = cache.get(question)

    if cached_entry:
        logger.info(f"Exact Cache HIT cho cau hoi: '{question[:50]}'")
        return {
            "cache_hit": True,
            "answer": cached_entry["answer"],
            "category": cached_entry.get("category", "DOMAIN_DATA"),
            "tool_intent": cached_entry.get("tool_intent"),
            "sources": cached_entry.get("sources", []),
            "retry_count": 0,
        }

    logger.debug("Cache MISS")
    return {"cache_hit": False, "retry_count": 0}


# ==============================================================================
# 2. QUERY ANALYSIS NODE
# ==============================================================================
def query_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("question", "")
    chat_history = state.get("chat_history", "")

    analyzed: AnalyzedQuery = analyze_query(question, chat_history=chat_history)
    logger.info(f"Query Analysis: domain={analyzed.domain}, code={analyzed.course_code}, targets={analyzed.targets}")

    return {
        "rewritten_question": analyzed.rewritten_query,
        "analyzed_query": analyzed.model_dump(),
    }


# ==============================================================================
# 3. ROUTER NODE
# ==============================================================================
def router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("rewritten_question") or state.get("question", "")
    analyzed_dict = state.get("analyzed_query", {})

    router_service = get_router_service()
    decision = router_service.classify(query=question, analyzed_query=analyzed_dict)

    logger.info(
        f"Router V2 Decision: category={decision.category}, "
        f"tool={decision.tool_intent}, path={decision.decision_path}, "
        f"reason={decision.reason_code}, confidence={decision.confidence}"
    )
    return {
        "category": decision.category,
        "tool_intent": decision.tool_intent,
    }


# ==============================================================================
# 4. RETRIEVE NODE
# ==============================================================================
def retrieve_node(state: Dict[str, Any]) -> Dict[str, Any]:
    analyzed_dict = state.get("analyzed_query", {})
    analyzed = AnalyzedQuery(**analyzed_dict) if analyzed_dict else analyze_query(state.get("question", ""))

    retry_count = state.get("retry_count", 0)
    validation_res = state.get("validation_result", {})
    missing_kws = validation_res.get("missing_keywords", [])

    # Nếu retry, mở rộng truy vấn bằng từ khóa thiếu
    if retry_count > 0 and missing_kws:
        enhanced = f"{analyzed.rewritten_query} {' '.join(missing_kws)}"
        logger.info(f"Retry {retry_count}: Enhanced query='{enhanced}'")
        analyzed.rewritten_query = enhanced

    candidates = retrieve_candidates(analyzed, top_k=settings.RETRIEVAL_CANDIDATES)
    return {"retrieved_docs": candidates}


# ==============================================================================
# 5. RERANK NODE
# ==============================================================================
def rerank_node(state: Dict[str, Any]) -> Dict[str, Any]:
    query_str = state.get("rewritten_question") or state.get("question", "")
    candidates = state.get("retrieved_docs", [])

    reranked = rerank_documents(query_str, candidates, top_k=settings.RERANK_TOP_K)
    return {"retrieved_docs": reranked}


# ==============================================================================
# 6. CONTEXT NODE
# ==============================================================================
def context_node(state: Dict[str, Any]) -> Dict[str, Any]:
    docs = state.get("retrieved_docs", [])
    analyzed_dict = state.get("analyzed_query", {})
    targets = analyzed_dict.get("targets", [])

    context_str, sources = build_context(
        docs, targets=targets, max_chunks=settings.CONTEXT_TOP_K
    )
    return {"context": context_str, "sources": sources}


# ==============================================================================
# 7. GROUNDED ANSWER NODE
# ==============================================================================
def grounded_answer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    context = state.get("context", "").strip()
    question = state.get("question", "")
    profile = state.get("student_profile", {})

    # Nếu không tìm thấy dữ liệu nào từ retrieval
    if not context or not state.get("retrieved_docs"):
        logger.info("Khong co context hop le -> Tu choi tra loi de tranh hallucination")
        return {
            "answer": "Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác.",
            "sources": [],
            "validation_result": {"valid": True}  # Không retry vì không có tài liệu
        }

    prompt = GROUNDED_ANSWER_PROMPT.format(
        student_profile=json.dumps(profile, ensure_ascii=False) if profile else "Chưa có",
        context=context,
        question=question,
    )

    answer = invoke_llm(prompt, temperature=settings.LLM_TEMPERATURE).strip()
    logger.info(f"Grounded answer generated ({len(answer)} chars)")

    # Nếu mô hình từ chối do thiếu dữ liệu, xóa sạch sources để tránh gán nhầm nguồn không liên quan
    if "chưa tìm thấy đủ dữ liệu" in answer.lower():
        return {
            "answer": "Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác.",
            "sources": [],
            "validation_result": {"valid": True},
        }

    return {"answer": answer}


# ==============================================================================
# 8. GENERAL ANSWER NODE
# ==============================================================================
def general_answer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("question", "")
    profile = state.get("student_profile", {})
    history = state.get("chat_history", "")

    prompt = GENERAL_ANSWER_PROMPT.format(
        student_profile=json.dumps(profile, ensure_ascii=False) if profile else "Chưa có",
        chat_history=history if history else "Cuộc trò chuyện mới",
        question=question,
    )

    answer = invoke_llm(prompt, temperature=0.3).strip()
    return {"answer": answer, "sources": []}


# ==============================================================================
# 9. VALIDATION NODE
# ==============================================================================
MAX_VALIDATION_RETRIES = 2


def validation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    answer = state.get("answer", "")
    context = state.get("context", "")
    question = state.get("question", "")
    retry_count = state.get("retry_count", 0)

    # 1. Nếu câu trả lời là từ chối hợp lệ hoặc không có context -> valid, không retry
    if "chưa tìm thấy đủ dữ liệu" in answer.lower() or not context:
        return {
            "validation_result": {"valid": True},
            "sources": [] if "chưa tìm thấy đủ dữ liệu" in answer.lower() else state.get("sources", []),
        }

    # 2. Thực hiện gọi LLM kiểm định
    is_valid = False
    data = {}
    try:
        prompt = VALIDATION_PROMPT.format(context=context, question=question, answer=answer)
        res_raw = invoke_llm(prompt, temperature=0.0).strip()
        cleaned = re.sub(r"```json|```", "", res_raw).strip()
        data = json.loads(cleaned)
        is_valid = bool(data.get("valid", False))
    except Exception as e:
        logger.warning(f"Validation error / malformed JSON: {e}. Coi la validation FAIL.")
        is_valid = False
        data = {"valid": False, "reason": f"Validator error: {e}", "missing_keywords": []}

    # 3. Nếu câu trả lời valid -> hoàn tất
    if is_valid:
        return {"validation_result": {"valid": True}}

    # 4. Nếu invalid nhưng còn lượt thử -> tăng retry_count và thử lại retrieval
    if retry_count < MAX_VALIDATION_RETRIES:
        logger.warning(
            f"Validation FAIL (lần {retry_count + 1}/{MAX_VALIDATION_RETRIES}): "
            f"{data.get('reason')}. Missing: {data.get('missing_keywords')}"
        )
        return {
            "validation_result": data,
            "retry_count": retry_count + 1,
        }

    # 5. Nếu invalid và ĐÃ HẾT LƯỢT THỬ (retry_count >= MAX_VALIDATION_RETRIES) -> BẮT BUỘC ABSTAIN
    logger.warning(f"Validation FAIL vượt quá giới hạn {MAX_VALIDATION_RETRIES} lần retry. Cưỡng chế ABSTAIN.")
    return {
        "answer": "Chưa tìm thấy đủ dữ liệu trong tài liệu hiện có để trả lời chính xác.",
        "sources": [],
        "validation_result": {"valid": True},  # valid=True để thoát retry loop sang save_chat
    }


# ==============================================================================
# 10. TOOL ACTION NODES (REMINDER & EMAIL)
# ==============================================================================
def parse_reminder_datetime(text: str) -> Optional[datetime.datetime]:
    now = datetime.datetime.now()
    text_lower = text.lower()

    hour = 8
    minute = 0
    time_matched = False

    time_match1 = re.search(r"(\d{1,2})[h:](\d{1,2})?", text_lower)
    if time_match1:
        hour = int(time_match1.group(1))
        if time_match1.group(2):
            minute = int(time_match1.group(2))
        time_matched = True
    else:
        time_match2 = re.search(r"(\d{1,2})\s*(?:giờ|h)", text_lower)
        if time_match2:
            hour = int(time_match2.group(1))
            time_matched = True

    date_matched = False
    target_date = None

    date_match = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{4}))?", text_lower)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else now.year
        if year < now.year:
            year = now.year
        try:
            target_date = datetime.date(year, month, day)
            date_matched = True
        except ValueError:
            target_date = None
    elif any(kw in text_lower for kw in ["ngày mai", "sáng mai", "chiều mai", "tối mai"]):
        target_date = (now + datetime.timedelta(days=1)).date()
        date_matched = True
    elif any(kw in text_lower for kw in ["hôm nay", "chiều nay", "tối nay"]):
        target_date = now.date()
        date_matched = True

    if not date_matched and not time_matched:
        return None

    if not date_matched:
        target_date = now.date()
        scheduled_dt = datetime.datetime.combine(target_date, datetime.time(hour=hour, minute=minute))
        if scheduled_dt <= now:
            scheduled_dt += datetime.timedelta(days=1)
        return scheduled_dt

    scheduled_dt = datetime.datetime.combine(target_date, datetime.time(hour=hour, minute=minute))
    if scheduled_dt <= now and date_match and not date_match.group(3):
        try:
            scheduled_dt = scheduled_dt.replace(year=scheduled_dt.year + 1)
        except ValueError:
            pass

    return scheduled_dt


def _reminder_job_callback(content: str, job_id: str):
    logger.info(f"[APScheduler Triggered] Lịch nhắc (ID {job_id}): {content}")


def parse_reminder_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("question", "")

    scheduled_dt = parse_reminder_datetime(question)
    if not scheduled_dt:
        return {
            "reminder_request": None,
            "answer": "Vui lòng cung cấp ngày hoặc giờ cụ thể bạn muốn đặt lịch nhắc (Ví dụ: 'Nhắc tôi nộp bài lúc 17h ngày 20/12' hoặc 'Nhắc tôi ôn thi sáng mai lúc 8h').",
            "sources": [],
        }

    job_id = f"remind_{uuid.uuid4().hex[:8]}"
    scheduled_str = scheduled_dt.strftime("%d/%m/%Y %H:%M")

    actual_job_id = schedule_reminder(
        run_date=scheduled_dt,
        func=_reminder_job_callback,
        args=[question, job_id],
    )

    if not actual_job_id:
        logger.error(f"Không thể đăng ký reminder job cho '{question}' tại {scheduled_str}")
        return {
            "reminder_request": None,
            "answer": "❌ Không thể tạo lịch nhắc nhở do hệ thống scheduler gặp lỗi nội bộ. Vui lòng thử lại sau.",
            "sources": [],
        }

    answer = f"✅ Đã lên lịch nhắc nhở thành công!\n- Nội dung: {question}\n- Thời gian: {scheduled_str}\n- Mã lịch nhắc: {actual_job_id}"
    return {
        "reminder_request": {
            "content": question,
            "scheduled_at": scheduled_str,
            "job_id": actual_job_id,
        },
        "answer": answer,
        "sources": [],
    }


def parse_email_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("question", "")

    # RÀNG BUỘC SỐ 31: Nếu EMAIL_ENABLED=false thì yêu cầu gửi email phải trả rõ:
    # "Chức năng email hiện chưa được cấu hình." Không crash.
    if not settings.EMAIL_ENABLED:
        logger.info("Email disabled -> Trả lời từ chối an toàn.")
        return {
            "answer": "Chức năng email hiện chưa được cấu hình.",
            "email_request": None,
            "sources": [],
        }

    # Nếu email được bật nhưng không tìm thấy địa chỉ người nhận -> Yêu cầu bổ sung, KHÔNG fallback email mặc định
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", question)
    if not email_match:
        return {
            "answer": "Vui lòng cung cấp địa chỉ email người nhận hợp lệ trong câu hỏi (Ví dụ: 'Gửi email tới giangvien@dainam.edu.vn').",
            "email_request": None,
            "sources": [],
        }

    recipient = email_match.group(0)
    res = _email_sender.send(recipient, "Thông báo từ Cố vấn học tập ĐNTU", question)
    if res.get("success"):
        answer = f"✅ Đã gửi email thành công tới {recipient}."
    else:
        answer = f"❌ Gửi email thất bại: {res.get('error')}"

    return {"answer": answer, "sources": []}


# ==============================================================================
# 11. SAVE CHAT NODE
# ==============================================================================
def save_chat_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("question", "")
    answer = state.get("answer", "")
    category = state.get("category", "DOMAIN_DATA")
    sources = state.get("sources", [])
    tool_intent = state.get("tool_intent")
    cache_hit = state.get("cache_hit", False)

    # Lưu Exact Cache nếu chưa có và không phải câu từ chối
    if not cache_hit and answer and "chưa tìm thấy đủ dữ liệu" not in answer.lower():
        cache = get_exact_cache()
        cache.set(
            key=question,
            answer=answer,
            category=category,
            sources=sources,
            tool_intent=tool_intent,
        )

    # Lưu vào Memory Manager
    memory = get_memory_manager()
    memory.update(question, answer)
    return {}
