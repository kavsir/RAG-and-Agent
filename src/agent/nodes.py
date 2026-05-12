import time
import re
import json
import datetime
import logging

from typing import List, Dict, Any, Optional

from src.prompts.intent_prompt import INTENT_PROMPT
from src.prompts.answer_prompt import ANSWER_PROMPT
from src.prompts.rewrite_prompt import REWRITE_PROMPT
from src.prompts.reflection_prompt import REFLECTION_PROMPT
from src.prompts.validation_prompt import VALIDATION_PROMPT

from src.rag.reranker import rerank
from src.rag.rag_pipeline import retrieve_docs
from src.memory.memory_manager import MemoryManager
from src.config.groq_gateway import invoke_llm
from src.cache.semantic_cache import SemanticCache
from src.cache.exact_cache import ExactCache
from src.tools.email_sender import EmailSender
from src.scheduler.reminder_scheduler import schedule_reminder, start_scheduler

# Thiết lập logging
logger = logging.getLogger(__name__)

# Debug flag – đặt False để tắt in debug, True để bật
DEBUG = True

memory_manager = MemoryManager()
_cache = ExactCache()
# Khởi tạo email sender
email_sender = EmailSender()
# Khởi động scheduler (nên gọi một lần khi app start)
start_scheduler()

def cache_node(state):
    start = time.time()
    question = state["question"]
    cached = _cache.get(question)
    if DEBUG: print(f"CACHE: {'HIT' if cached else 'MISS'}")
    
    result = {
        "skip_pipeline": bool(cached),
        "cache_hit": bool(cached),
        "answer": cached or "",
        "retry_count": 0  # Initialize retry_count
    }
    
    if cached:
        result["answer"] = cached
    
    elapsed = time.time() - start
    if DEBUG: print(f"cache_node took {elapsed:.2f}s")
    return result

def rewrite_node(state):
    start = time.time()
    if DEBUG: print("=== REWRITE NODE ===")
    if DEBUG: print("Input question:", state.get("question"))
    question = state["question"]

    prompt = REWRITE_PROMPT.format(question=question)
    rewritten = invoke_llm(prompt).strip()
    rewritten = rewritten.split('\n')[0].strip()

    if not rewritten or len(rewritten) < 3:
        rewritten = question

    if DEBUG: print("Rewritten question:", rewritten)
    elapsed = time.time() - start
    if DEBUG: print(f"rewrite_node took {elapsed:.2f}s")
    return {"rewritten_question": rewritten}

# Định nghĩa các intent hợp lệ
VALID_INTENTS = {
    "lecturer_info", "course_info_basic", "course_info_full",
    "course_plan", "regulation", "grade_inquiry", "schedule",
    "greeting", "general_question", "set_reminder", "send_email"
}

# Thứ tự ưu tiên cho primary intent
PRIORITY_ORDER = [
    "lecturer_info",
    "course_info_full",    # ưu tiên cao hơn course_plan
    "course_info_basic",
    "course_plan",         # thấp hơn course_info_full
    "regulation",
    "grade_inquiry",
    "schedule",
    "send_email",
    "set_reminder",
    "greeting",
    "general_question"
]

def intent_node(state):
    """
    Phân loại câu hỏi thành 2 nhóm chính:
    - DOMAIN_DATA: Câu hỏi về dữ liệu nội bộ (yêu cầu RAG)
    - GENERAL_LLM: Câu hỏi về kiến thức chung (LLM đủ xử lý)
    """
    start = time.time()
    question = state["rewritten_question"]
    prompt = INTENT_PROMPT.format(question=question)
    raw_response = invoke_llm(prompt).strip()
    
    print(f"🤖 Raw intent response:\n{raw_response}\n")
    
    # Bước 1: Loại bỏ markdown
    cleaned = re.sub(r'```json|```', '', raw_response).strip()
    
    category = "GENERAL_LLM"  # default
    
    # Bước 2: Thử parse JSON để lấy category
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            category = data.get("category", "GENERAL_LLM").upper()
        elif isinstance(data, str):
            category = data.upper()
    except json.JSONDecodeError:
        # Bước 3: Fallback - tìm từ khóa trong response
        if "DOMAIN_DATA" in raw_response.upper():
            category = "DOMAIN_DATA"
        elif "GENERAL_LLM" in raw_response.upper():
            category = "GENERAL_LLM"
        else:
            # Bước 4: Sử dụng heuristics để quyết định
            # Nếu câu hỏi có các từ liên quan dữ liệu nội bộ
            domain_keywords = [
                "giảng viên", "ai dạy", "mã môn", "mã học phần", "tín chỉ",
                "clo", "chuẩn đầu ra", "lịch biểu", "kế hoạch", "quy chế",
                "quy định", "điểm", "tài liệu tham khảo", "nội dung", "mục tiêu",
                "học phần", "môn học", "khoa", "trường đại học đại nam"
            ]
            question_lower = question.lower()
            if any(kw in question_lower for kw in domain_keywords):
                category = "DOMAIN_DATA"
            else:
                category = "GENERAL_LLM"
    
    # Bước 5: Validate category
    if category not in ["DOMAIN_DATA", "GENERAL_LLM"]:
        category = "GENERAL_LLM"  # safety fallback
    
    print(f"🔥 Intent Category: {category}")
    elapsed = time.time() - start
    if DEBUG: print(f"intent_node took {elapsed:.2f}s")
    
    return {
        "category": category,  # DOMAIN_DATA hoặc GENERAL_LLM
        "intent": category  # legacy support
    }

def memory_node(state):
    # KHÔNG cập nhật profile từ chat nữa – chỉ lấy profile hiện tại
    profile = memory_manager.profile.get_profile() or {}
    history = memory_manager.chat.get_history()

    history_text = "\n".join(
        f"User: {h['user']}\nAI: {h['ai']}"
        for h in history[-5:]
    )
    return {
        "student_profile": profile,
        "chat_history": history_text
    }

def retrieve_node(state):
    start = time.time()
    if DEBUG: print("=== RETRIEVE NODE ===")
    question = state["rewritten_question"]
    intent = state.get("intent")
    regenerate_count = state.get("regenerate_count", 0)

    missing_info = state.get("validation_result", {}).get("missing_info", [])
    if regenerate_count > 0 and missing_info:
        extra_keywords = " ".join(missing_info)
        enhanced_query = f"{question} {extra_keywords}"
        if DEBUG: print(f"Enhanced query: {enhanced_query}")
    else:
        enhanced_query = question

    if regenerate_count == 0:
        top_k = 30   # giảm từ 50 xuống 30
    elif regenerate_count == 1:
        top_k = 40
    else:
        top_k = 50

    try:
        docs = retrieve_docs(enhanced_query, intent=intent, top_k=top_k) or []
        if DEBUG: print(f"Retrieved {len(docs)} docs")
        if docs and DEBUG:
            print("First doc:", docs[0].get('text')[:200] if isinstance(docs[0], dict) else "Not dict")
        # docs = rerank(enhanced_query, docs, top_k=10) if docs else []
        if DEBUG: print(f"After rerank: {len(docs)} docs")
    except Exception as e:
        if DEBUG:
            print("!!! LỖI trong retrieve_node:", e)
            import traceback
            traceback.print_exc()
        docs = []

    if DEBUG:
        for idx, d in enumerate(docs):
            if "CLO" in d['text']:
                print(f"CLO chunk ở vị trí {idx}")
            if "II. Thông tin giảng viên" in d['text']:
                print(f"Teacher info chunk ở vị trí {idx}")

    new_count = regenerate_count + 1
    elapsed = time.time() - start
    if DEBUG: print(f"retrieve_node took {elapsed:.2f}s")
    return {"retrieved_docs": docs, "regenerate_count": new_count}
def context_node(state):
    """
    Xây dựng context từ retrieved_docs.
    Nếu không có docs (GENERAL_LLM case), trả về context rỗng.
    """
    docs = state.get("retrieved_docs", [])
    
    # Nếu không có docs (ví dụ: GENERAL_LLM đã bỏ qua retrieve_node)
    if not docs:
        if DEBUG: print("⚠️ No docs retrieved - context_node returns empty context")
        return {"context": ""}

    # Tìm các chunk quan trọng
    clo_chunk = None
    teacher_chunk = None
    schedule_chunks = []  # danh sách các chunk kế hoạch
    for doc in docs:
        text = doc['text']
        if "V. Chuẩn đầu ra học phần" in text or "Chuẩn đầu ra học phần" in text:
            clo_chunk = text
        if "II. Thông tin giảng viên" in text:
            teacher_chunk = text
        if "VII. Kế hoạch giảng dạy" in text:
            schedule_chunks.append(text)
        elif "Tuần" in text and "Kế hoạch giảng dạy" not in text:
            # Có thể các chunk con theo tuần
            schedule_chunks.append(text)

    # Ưu tiên kế hoạch giảng dạy lên đầu, lấy toàn bộ không cắt
    context_parts = []
    if schedule_chunks:
        # Gộp tất cả chunk kế hoạch lại
        full_schedule = "\n\n".join(schedule_chunks)
        context_parts.append(f"[KẾ HOẠCH GIẢNG DẠY]\n{full_schedule}")
    if clo_chunk:
        context_parts.append(f"[CHUẨN ĐẦU RA]\n{clo_chunk}")
    if teacher_chunk:
        context_parts.append(f"[GIẢNG VIÊN]\n{teacher_chunk}")

    # Thêm các docs khác (giới hạn 10 docs, mỗi doc 1500 ký tự)
    added = set(schedule_chunks) | ({clo_chunk} if clo_chunk else set()) | ({teacher_chunk} if teacher_chunk else set())
    for i, d in enumerate(docs[:15]):
        if d['text'] in added:
            continue
        text = d['text'][:1500]
        source = d['metadata'].get('source_file', 'Unknown')
        context_parts.append(f"[Document {i+1} từ {source}]\n{text}")
        if len(context_parts) >= 15:
            break

    context = "\n\n".join(context_parts)
    print(f"Context length: {len(context)} chars")
    # In preview để debug
    print(f"Context preview (first 800 chars):\n{context[:800]}...")
    return {"context": context}

def answer_node(state):
    """
    Trả lời dựa trên category:
    - DOMAIN_DATA (with context): Trả lời dựa trên tài liệu từ RAG
    - GENERAL_LLM (no context): Trả lời dựa trên kiến thức chung của mô hình
    """
    start = time.time()
    if DEBUG: print("=== ANSWER NODE ===")
    question = state["question"]
    context = state.get("context", "")
    profile = state.get("student_profile", {})
    history = state.get("chat_history", "")
    category = state.get("category", "GENERAL_LLM")

    # TRƯỜNG HỢP 1: DOMAIN_DATA - Câu hỏi cần dữ liệu từ RAG
    if category == "DOMAIN_DATA" and context:
        question_lower = question.lower()
        
        # Xác định chủ đề để tạo prompt chuyên biệt
        if any(kw in question_lower for kw in ["giảng viên", "ai dạy", "thầy", "cô"]):
            topic = "giảng viên"
        elif any(kw in question_lower for kw in ["kế hoạch giảng dạy", "lịch học", "tuần", "schedule"]):
            topic = "kế hoạch giảng dạy"
        elif any(kw in question_lower for kw in ["chuẩn đầu ra", "clo", "course learning outcome"]):
            topic = "chuẩn đầu ra"
        elif "mục tiêu" in question_lower:
            topic = "mục tiêu"
        elif "tín chỉ" in question_lower:
            topic = "tín chỉ"
        elif "nội dung" in question_lower:
            topic = "nội dung"
        else:
            topic = "thông tin chung"

        # Prompt cực kỳ chặt chẽ cho DOMAIN_DATA
        if topic == "kế hoạch giảng dạy":
            prompt = f"""Bạn là trợ lý cố vấn học tập. Hãy trả lời câu hỏi dựa trên tài liệu tham khảo.

**Yêu cầu trả lời:**
- BẮT BUỘC: Chỉ trả về nội dung của phần "Kế hoạch giảng dạy".
- Nếu tài liệu có kế hoạch giảng dạy, hãy liệt kê chi tiết từng tuần: tuần, nội dung, hoạt động, yêu cầu chuẩn bị, chuẩn đầu ra liên quan.
- **TUYỆT ĐỐI KHÔNG ĐƯỢC đề cập đến bất kỳ thông tin nào khác** (giảng viên, tín chỉ, mục tiêu, CLO, tài liệu).
- **CẤM** sử dụng cụm từ "không có thông tin" nếu tài liệu đã có dữ liệu về kế hoạch giảng dạy.
- Nếu tài liệu có kế hoạch giảng dạy nhưng bạn không thấy, hãy kiểm tra lại các đoạn văn có chứa "Tuần" hoặc "Kế hoạch giảng dạy".

**Tài liệu tham khảo:**
{context}

**Câu hỏi:** {question}

**Trả lời:**"""
        elif topic == "giảng viên":
            prompt = f"""Bạn là trợ lý cố vấn học tập. Hãy trả lời câu hỏi dựa trên tài liệu tham khảo.

**Yêu cầu trả lời:**
- BẮT BUỘC: Chỉ trả về thông tin giảng viên (họ tên, học vị, email, đơn vị).
- **TUYỆT ĐỐI KHÔNG ĐƯỢC đề cập đến tín chỉ, CLO, mục tiêu, kế hoạch giảng dạy**.
- Nếu tài liệu có thông tin giảng viên, hãy trình bày đầy đủ.
- Chỉ nói "Không có thông tin giảng viên" nếu thực sự không tìm thấy trong context.

**Tài liệu tham khảo:**
{context}

**Câu hỏi:** {question}

**Trả lời:**"""
        else:
            # Prompt chung cho các topic khác từ DOMAIN_DATA
            prompt = f"""Bạn là trợ lý cố vấn học tập. Hãy trả lời câu hỏi dựa trên tài liệu tham khảo.

**Yêu cầu trả lời:**
- BẮT BUỘC: Chỉ cung cấp thông tin về {topic}.
- **TUYỆT ĐỐI KHÔNG ĐƯỢC đề cập đến các thông tin khác ngoài {topic}** nếu chúng không liên quan.
- Chỉ nói "Không có thông tin về {topic}" nếu thực sự không tìm thấy trong context.
- Ưu tiên dữ liệu từ tài liệu, không bổ sung kiến thức ngoài.

**Tài liệu tham khảo:**
{context}

**Câu hỏi:** {question}

**Trả lời:**"""
        
        answer = invoke_llm(prompt).strip()

    # TRƯỜNG HỢP 2: GENERAL_LLM - Câu hỏi kiến thức chung
    else:
        prompt = f"""Bạn là trợ lý cố vấn học tập của sinh viên khoa CNTT, Trường Đại học Đại Nam.
Bạn thân thiện, hữu ích, và chuyên nghiệp.

Trả lời câu hỏi sau bằng cách sử dụng kiến thức chung của bạn. 
Đừng nói "không có dữ liệu" - hãy cung cấp câu trả lời đầy đủ, chính xác giảm thiểu "hallucination".

**Hướng dẫn:**
- Nếu là chào hỏi: Trả lời thân thiện, tích cực
- Nếu là kiến thức kỹ thuật (Dijkstra, Python, Database, etc.): Giải thích rõ ràng, dễ hiểu, kèm ví dụ nếu cần
- Nếu là lý thuyết: Cung cấp giải thích toàn diện
- Nếu là vấn đề xã hội: Đưa ra quan điểm cân bằng, hữu ích
- Luôn sử dụng tiếng Việt, lịch sự

**Thông tin sinh viên:**
{profile if profile else "Chưa có thông tin"}

**Lịch sử chat (5 tin nhắn cuối):**
{history if history else "Đây là cuộc trò chuyện mới"}

**Câu hỏi:** {question}

**Trả lời:**"""
        
        answer = invoke_llm(prompt).strip()

    if DEBUG: print("Answer generated:", answer[:200])
    elapsed = time.time() - start
    if DEBUG: print(f"answer_node took {elapsed:.2f}s")
    return {"answer": answer}

def reflection_node(state):
    start = time.time()
    context = state["context"]
    answer = state["answer"]
    prompt = REFLECTION_PROMPT.format(context=context, answer=answer)
    result = invoke_llm(prompt).strip()
    elapsed = time.time() - start
    if DEBUG: print(f"reflection_node took {elapsed:.2f}s")
    return {"reflection": result or "ok"}


def save_chat_node(state):
    question = state["question"]
    answer = state["answer"]

    if not state.get("skip_pipeline", False):
        _cache.set(question, answer)

    memory_manager.update(question, answer)
    return {}

def parse_reminder_node(state):
    """
    Phân tích câu hỏi để lấy thông tin lịch nhắc.
    Stress test: Validate email format và date format
    """
    if DEBUG: print("=== PARSE REMINDER NODE ===")
    question = state["question"]
    profile = state.get("student_profile", {})
    retry_count = state.get("retry_count", 0)
    MAX_RETRIES = 3

    # Kiểm tra số lần retry để tránh infinite loop
    if retry_count >= MAX_RETRIES:
        return {
            "reminder_requests": [],
            "answer": f"❌ Không thể xử lý yêu cầu nhắc nhở sau {MAX_RETRIES} lần cố gắng. Vui lòng thử lại sau.",
            "retry_count": retry_count
        }

    # Lấy email từ profile
    email = profile.get("email", "").strip()
    
    # ⚠️ STRESS TEST 1: Validate email format
    def is_valid_email(email_str):
        """
        Kiểm tra format email cơ bản
        - Phải có @ và .
        - Không chứa @@, @., .@
        - Phải có text trước @
        - Phải có domain sau @
        """
        if not email_str or len(email_str) < 5:
            return False
        if email_str.count('@') != 1:  # Chỉ có đúng 1 @
            return False
        if '@@' in email_str or '@.' in email_str or '.@' in email_str:  # Invalid patterns
            return False
        
        parts = email_str.split('@')
        if len(parts[0]) < 2 or len(parts[1]) < 3:  # local@domain.ext
            return False
        
        if '.' not in parts[1]:  # domain phải có dấu chấm
            return False
        
        return True
    
    if not email or not is_valid_email(email):
        return {
            "reminder_requests": [],
            "answer": f"❌ Email không hợp lệ: '{email}'. Vui lòng cập nhật email hợp lệ (vd: student@dainam.edu.vn).",
            "retry_count": retry_count
        }

    # ⚠️ STRESS TEST 2: Extract date with validation
    date_match = re.search(r'(\d{1,2})/(\d{1,2})', question)
    if not date_match:
        return {
            "reminder_requests": [],
            "answer": "❌ Định dạng ngày không hợp lệ. Vui lòng nhập ngày theo định dạng dd/mm (ví dụ: 25/12).",
            "retry_count": retry_count + 1
        }

    day, month = int(date_match.group(1)), int(date_match.group(2))
    
    # ⚠️ STRESS TEST 3: Validate date values
    if day < 1 or day > 31 or month < 1 or month > 12:
        return {
            "reminder_requests": [],
            "answer": f"❌ Ngày tháng không hợp lệ: {day}/{month}. Vui lòng nhập ngày (1-31) và tháng (1-12).",
            "retry_count": retry_count + 1
        }
    
    # Try to create valid date
    try:
        now = datetime.datetime.now()
        year = now.year
        if month < now.month or (month == now.month and day < now.day):
            year += 1
        exam_date = datetime.datetime(year, month, day)
        
        # Đảm bảo ngày nhắc không quá xa (tối đa 1 năm)
        if exam_date > now + datetime.timedelta(days=365):
            return {
                "reminder_requests": [],
                "answer": f"❌ Ngày {day}/{month} quá xa (hơn 1 năm). Vui lòng nhập ngày gần hơn.",
                "retry_count": retry_count + 1
            }
    except ValueError as e:
        logger.error(f"Invalid date {day}/{month}: {e}")
        return {
            "reminder_requests": [],
            "answer": f"❌ Ngày tháng không hợp lệ: {day}/{month}. Lỗi: {str(e)}",
            "retry_count": retry_count + 1
        }

    # Số ngày nhắc trước (mặc định 2)
    days_before = 2
    days_match = re.search(r'trước\s+(\d+)\s+ngày', question)
    if days_match:
        try:
            days_before = int(days_match.group(1))
            if days_before < 0 or days_before > 30:
                return {
                    "reminder_requests": [],
                    "answer": f"❌ Số ngày nhắc không hợp lệ: {days_before}. Vui lòng nhập từ 0-30 ngày.",
                    "retry_count": retry_count + 1
                }
        except (ValueError, IndexError):
            days_before = 2

    reminder_time = exam_date - datetime.timedelta(days=days_before)
    
    # ⚠️ STRESS TEST 4: Validate reminder time is in future
    if reminder_time <= now:
        return {
            "reminder_requests": [],
            "answer": f"❌ Thời điểm nhắc đã qua. Vui lòng chọn ngày trong tương lai.",
            "retry_count": retry_count + 1
        }

    # Tạo nội dung email
    subject = "Nhắc lịch thi"
    body = f"""Bạn có lịch thi vào ngày {exam_date.strftime('%d/%m/%Y')}.
Email này được gửi để nhắc bạn chuẩn bị tốt cho kỳ thi.

-- Trợ lý cố vấn học tập"""

    # Trả về reminder_requests và câu trả lời
    return {
        "reminder_requests": [{
            "to": email,
            "reminder_time": reminder_time.isoformat(),
            "subject": subject,
            "body": body
        }],
        "answer": f"✅ Đã đặt lịch nhắc qua email vào ngày {exam_date.strftime('%d/%m/%Y')} (nhắc trước {days_before} ngày). Bạn sẽ nhận được email nhắc nhở.",
        "retry_count": 0  # Reset khi thành công
    }

def reminder_node(state):
    """
    Lên lịch gửi email nhắc.
    """
    if DEBUG: print("=== REMINDER NODE ===")
    requests = state.get("reminder_requests", [])
    results = []

    for req in requests:
        to = req["to"]
        reminder_time = datetime.datetime.fromisoformat(req["reminder_time"])
        subject = req["subject"]
        body = req["body"]

        # Hàm gửi email thật (sẽ được gọi bởi scheduler)
        def send_email():
            email_sender.send(to, subject, body)

        # Lên lịch
        job_id = schedule_reminder(reminder_time, send_email, [])
        results.append({
            "to": to,
            "scheduled_at": reminder_time.isoformat(),
            "job_id": job_id
        })
        print(f"📅 Reminder scheduled for {reminder_time} to {to}")

    return {"reminder_results": results}

def parse_email_request_node(state):
    """
    Phân tích yêu cầu gửi email.
    Stress test: Validate email format, dụi nhân địa chỉ, độ dài nội dung
    """
    if DEBUG: print("=== PARSE EMAIL REQUEST NODE ===")
    question = state["question"]
    profile = state.get("student_profile", {})
    retry_count = state.get("retry_count", 0)
    MAX_RETRIES = 3
    
    # Kiểm tra số lần retry
    if retry_count >= MAX_RETRIES:
        return {
            "email_requests": [],
            "answer": f"❌ Không thể xử lý yêu cầu gửi email sau {MAX_RETRIES} lần cố gắng. Vui lòng thử lại sau.",
            "retry_count": retry_count
        }

    user_email = profile.get("email", "").strip()
    user_name = profile.get("name", "Sinh viên")

    # ⚠️ STRESS TEST 1: Validate sender email
    def is_valid_email(email_str):
        """Kiểm tra format email cơ bản"""
        if not email_str or len(email_str) < 5:
            return False
        if email_str.count('@') != 1:
            return False
        if '@@' in email_str or '@.' in email_str or '.@' in email_str:
            return False
        
        parts = email_str.split('@')
        if len(parts[0]) < 2 or len(parts[1]) < 3:
            return False
        if '.' not in parts[1]:
            return False
        return True
    
    # ⚠️ STRESS TEST 2: Find recipient emails
    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    emails_found = re.findall(email_pattern, question)
    
    # Filter valid emails
    valid_recipient_emails = []
    for email in emails_found:
        if is_valid_email(email):
            valid_recipient_emails.append(email)
    
    if not valid_recipient_emails:
        if emails_found:
            # Có email nhưng format sai
            invalid_emails = ", ".join(emails_found)
            return {
                "email_requests": [],
                "answer": f"❌ Định dạng email người nhận không hợp lệ: {invalid_emails}. Ví dụ email hợp lệ: student@dainam.edu.vn",
                "retry_count": retry_count + 1
            }
        else:
            return {
                "email_requests": [],
                "answer": "❌ Không tìm thấy địa chỉ email người nhận. Vui lòng cung cấp email đích (vd: friend@dainam.edu.vn).",
                "retry_count": retry_count + 1
            }

    # ⚠️ STRESS TEST 3: Validate sender email
    if not user_email or not is_valid_email(user_email):
        return {
            "email_requests": [],
            "answer": f"❌ Email của bạn không hợp lệ: '{user_email}'. Vui lòng cập nhật email hợp lệ trong profile trước khi gửi email.",
            "retry_count": retry_count + 1
        }

    # ⚠️ STRESS TEST 4: Prevent sending to self
    if user_email in valid_recipient_emails:
        valid_recipient_emails = [e for e in valid_recipient_emails if e != user_email]
        if not valid_recipient_emails:
            return {
                "email_requests": [],
                "answer": "❌ Không thể gửi email cho chính mình. Vui lòng chỉ định người nhận khác.",
                "retry_count": retry_count + 1
            }

    # Xác định loại email
    question_lower = question.lower()
    if 'chúc mừng sinh nhật' in question_lower:
        email_type = "birthday"
    elif 'cảm ơn' in question_lower:
        email_type = "thank_you"
    elif 'nhắc' in question_lower or 'nhắc nhở' in question_lower:
        email_type = "reminder"
    else:
        email_type = "general"

    # ⚠️ STRESS TEST 5: Generate or validate email content
    from src.prompts.email_composition_prompt import EMAIL_COMPOSITION_PROMPT
    prompt = EMAIL_COMPOSITION_PROMPT.format(
        request=question,
        sender_name=user_name,
        sender_email=user_email,
        recipient_email="<RECIPIENT_EMAIL>",
        email_type=email_type
    )
    
    try:
        email_content = invoke_llm(prompt).strip()
    except Exception as e:
        logger.error(f"Error generating email content: {e}")
        email_content = None

    # ⚠️ STRESS TEST 6: Fallback nếu LLM thất bại hoặc trả về rỗng
    if not email_content or len(email_content) < 20:
        if DEBUG: print("⚠️ LLM returned empty/short email, using fallback")
        
        if email_type == "birthday":
            subject = f"🎂 Chúc mừng sinh nhật!"
            body = f"""Chào bạn,

Nhân dịp sinh nhật của bạn, tôi gửi đến bạn những lời chúc tốt đẹp nhất.

Chúc bạn luôn vui vẻ, hạnh phúc và thành công!

Trân trọng,
{user_name}"""
        elif email_type == "thank_you":
            subject = "Cảm ơn bạn"
            body = f"""Kính gửi bạn,

Xin cảm ơn bạn vì sự hỗ trợ quý báu. Tôi rất trân trọng điều này.

Trân trọng,
{user_name}"""
        elif email_type == "reminder":
            subject = "Nhắc nhở"
            body = f"""Kính gửi bạn,

Đây là email nhắc nhở về lịch thi/hạn nộp bài sắp tới. Vui lòng chuẩn bị sẵn sàng.

Trân trọng,
{user_name}"""
        else:
            subject = f"Thông báo từ {user_name}"
            body = f"""{question}

Trân trọng,
{user_name}"""
        
        email_content = f"Subject: {subject}\n\n{body}"

    # Tạo email_requests từng người nhận
    email_requests = []
    for recipient in valid_recipient_emails:
        personalized_content = email_content.replace("<RECIPIENT_EMAIL>", recipient)
        email_requests.append({
            "to": recipient,
            "content": personalized_content
        })

    # Câu trả lời
    if len(valid_recipient_emails) == 1:
        answer = f"✅ Đã chuẩn bị email gửi đến {valid_recipient_emails[0]}. Đang tiến hành gửi..."
    else:
        answer = f"✅ Đã chuẩn bị email gửi đến {len(valid_recipient_emails)} người nhận. Đang tiến hành gửi..."

    return {
        "email_requests": email_requests,
        "answer": answer,
        "retry_count": 0  # Reset khi thành công
    }

def send_email_node(state):
    if DEBUG: print("=== SEND EMAIL NODE ===")
    requests = state.get("email_requests", [])
    results = []
    success_list = []
    fail_list = []
    
    for req in requests:
        to = req["to"]
        content = req["content"]
        lines = content.split('\n', 2)
        subject = lines[0].replace("Subject:", "").strip() if lines[0].startswith("Subject:") else "Thông báo"
        body = lines[2] if len(lines) > 2 else content
        try:
            result = email_sender.send(to, subject, body)
            results.append(result)
            if result.get("success"):
                success_list.append(to)
            else:
                fail_list.append(to)
        except Exception as e:
            logger.error(f"Exception in send_email_node: {e}")
            results.append({"success": False, "error": str(e), "to": to})
            fail_list.append(to)
    
    # Tạo câu trả lời tổng hợp
    answer_parts = []
    if success_list:
        answer_parts.append(f"✅ Đã gửi email thành công đến: {', '.join(success_list)}")
    if fail_list:
        answer_parts.append(f"❌ Gửi email thất bại đến: {', '.join(fail_list)}")
    if not success_list and not fail_list:
        answer_parts.append("❌ Không có email nào được gửi.")
    
    answer = "\n".join(answer_parts)
    return {"email_results": results, "answer": answer}

def validation_node(state):
    """
    Validate answer quality with Chain-of-Thought reasoning.
    Prevent infinite loops with retry_count monitoring.
    """
    start = time.time()
    if DEBUG: print("=== VALIDATION NODE ===")
    context = state.get("context", "")
    answer = state.get("answer", "")
    retry_count = state.get("retry_count", 0)
    regenerate_count = state.get("regenerate_count", 0)
    
    # ⚠️ Safety check: Maximum retry attempts
    MAX_RETRIES = 3
    if retry_count >= MAX_RETRIES:
        if DEBUG: print(f"⚠️ Max retries ({MAX_RETRIES}) reached. Accepting answer.")
        return {
            "validation_result": {
                "valid": True,  # Force accept to avoid infinite loop
                "feedback": "Max retries reached",
                "max_retries_exceeded": True
            },
            "retry_count": retry_count
        }

    if not context or not answer:
        return {
            "validation_result": {
                "valid": False,
                "feedback": "Missing context or answer - fatal error"
            },
            "retry_count": retry_count
        }

    prompt = VALIDATION_PROMPT.format(context=context, answer=answer)
    try:
        result_text = invoke_llm(prompt, temperature=0).strip()
        
        # Try to parse JSON response
        if result_text.startswith('{'):
            import json
            result_dict = json.loads(result_text)
            
            if result_dict.get("missing_info"):
                # Missing information, can regenerate
                missing_parts = result_dict["missing_info"]
                return {
                    "validation_result": {
                        "valid": False,
                        "missing_info": missing_parts,
                        "feedback": f"Missing: {', '.join(missing_parts)}"
                    },
                    "retry_count": retry_count + 1
                }
            elif result_dict.get("errors"):
                # Has errors
                errors = result_dict["errors"]
                return {
                    "validation_result": {
                        "valid": False,
                        "errors": errors,
                        "feedback": f"Errors: {', '.join(errors)}"
                    },
                    "retry_count": retry_count + 1
                }
            else:
                # Valid answer
                return {
                    "validation_result": {"valid": True},
                    "retry_count": 0  # Reset counter on success
                }
        else:
            # Text-based response
            valid = "VALID" in result_text.upper()
            return {
                "validation_result": {
                    "valid": valid,
                    "feedback": result_text
                },
                "retry_count": 0 if valid else retry_count + 1
            }
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse validation JSON: {e}")
        # Fallback: accept answer to avoid stuck state
        return {
            "validation_result": {
                "valid": True,
                "feedback": "Could not parse validation response"
            },
            "retry_count": retry_count
        }
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return {
            "validation_result": {
                "valid": True,
                "feedback": f"Validation error: {str(e)}"
            },
            "retry_count": retry_count
        }
    finally:
        elapsed = time.time() - start
        if DEBUG: print(f"validation_node took {elapsed:.2f}s (retry_count: {retry_count})")