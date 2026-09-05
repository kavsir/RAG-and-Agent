# 🚀 Nâng cấp hệ thống Router - LangGraph

**Ngày cập nhật:** 26/03/2026  
**Mục tiêu:** Phân loại thông minh giữa DOMAIN_DATA (cần RAG) vs GENERAL_LLM (kiến thức chung)

---

## 📋 Tóm tắt thay đổi

### 1. **System Prompt - Intent Classification (intent_prompt.py)**
✅ **Cập nhật hoàn toàn** - 2 category chính:

```
NHÓM 1: DOMAIN_DATA (Dữ liệu nội bộ - BẮT BUỘC dùng RAG)
├── Thông tin GIẢNG VIÊN (ai dạy, email, bộ môn)
├── Thông tin MÔN HỌC CỤ THỂ (mã môn, tín chỉ, CLO, lịch biểu)
├── CHƯƠNG TRÌNH ĐÀO TẠO (danh sách môn theo kỳ)
├── QUY CHỈ/QUY ĐỊNH (điểm, điều kiện tốt nghiệp)
└── LỊCH HỌC/LỊCH THI

NHÓM 2: GENERAL_LLM (Kiến thức chung - TRẢ LỜI CÓ VĂN BẢN)
├── Kiến thức kỹ thuật (Dijkstra, Python, Database)
├── CHÀO HỎI (Xin chào, Bạn khỏe không)
├── LÝ THUYẾT CHUNG (Lập trình là gì, AI là gì)
├── VẤN ĐỀ XÃ HỘI (Quan điểm, sự kiện)
└── GIÚP TRỢ VĂN BẢN (Viết email, Cách nộp hồ sơ)
```

---

### 2. **Intent Node (nodes.py - `intent_node`)**
✅ **Viết lại hoàn toàn:**

- Input: `rewritten_question`
- LLM Classification: Gọi Groq/Llama với INTENT_PROMPT mới
- Fallback Heuristics: Nếu LLM parse bất thành công, dùng từ khóa để quyết định
- Output: 
  - `category` = "DOMAIN_DATA" | "GENERAL_LLM"
  - `intent` = category (legacy support)

**Logic:**
```python
category = invoke_llm(INTENT_PROMPT)  # JSON: {"category": "..."}
|
├─ Nếu DOMAIN_DATA → Cần RAG
└─ Nếu GENERAL_LLM → Bỏ qua RAG, dùng kiến thức mô hình
```

---

### 3. **Graph Router (graph.py - `route_after_intent`)**
✅ **Cấu trúc lại hoàn toàn:**

**Trước:**
```
intent_node 
  ↓ (route_after_intent)
  ├─ set_reminder → parse_reminder
  ├─ send_email → parse_email_request
  ├─ RAG intents → retrieve
  └─ others → answer
```

**Sau:**
```
intent_node
  ↓ (route_after_intent - dựa trên CATEGORY)
  ├─ DOMAIN_DATA → retrieve → context → answer → validation → save_chat
  └─ GENERAL_LLM → (bỏ qua retrieve) → answer → save_chat
```

**Routing Logic:**
```python
def route_after_intent(state):
    category = state.get("category", "GENERAL_LLM")
    if category == "DOMAIN_DATA":
        return "retrieve"  # Bắt buộc dùng RAG
    else:
        return "answer"    # Bỏ qua retrieve, đi thẳng answer
```

---

### 4. **Answer Node (nodes.py - `answer_node`)**
✅ **Cập nhật xử lý 2 case:**

**CASE 1: DOMAIN_DATA (with context)**
```python
if category == "DOMAIN_DATA" and context:
    # Prompt chuyên biệt theo topic (giảng viên, kế hoạch, CLO, etc.)
    # - BẮT BUỘC: Chỉ trả về thông tin từ CONTEXT
    # - TUYỆT ĐỐI: Không bổ sung kiến thức ngoài
    # - Lỗi: Nếu không có thông tin, nói rõ "Không có thông tin..."
    prompt = DOMAIN_PROMPT[topic]  # Chặt chẽ, focused
```

**CASE 2: GENERAL_LLM (no context)**
```python
else:  # GENERAL_LLM
    # Prompt rộng mở, hướng LLM sử dụng kiến thức chung
    # - Kiến thức kỹ thuật: Giải thích rõ ràng, kèm ví dụ
    # - Chào hỏi: Trả lời thân thiện, tích cực
    # - Lý thuyết: Giải thích toàn diện
    prompt = GENERAL_LLM_PROMPT
```

---

### 5. **Context Node (nodes.py - `context_node`)**
✅ **Thêm safety check:**

```python
def context_node(state):
    docs = state.get("retrieved_docs", [])
    if not docs:
        return {"context": ""}  # ← Safety: GENERAL_LLM sẽ bỏ qua retrieve
    # ... xử lý docs bình thường
```

---

### 6. **State TypeDict (state.py - AgentState)**
✅ **Thêm field mới:**

```python
category: str  # DOMAIN_DATA | GENERAL_LLM
```

---

### 7. **Graph Conditional Routing (graph.py - `route_after_answer`)**
✅ **Điều hướng sau answer:**

```python
def route_after_answer(state):
    category = state.get("category", "GENERAL_LLM")
    if category == "DOMAIN_DATA":
        return "validation"  # Cần kiểm tra câu trả lời có đầy đủ không
    else:
        return "save_chat"   # GENERAL_LLM không cần validation
```

---

### 8. **Windows Path Handling ✅**

Toàn bộ các file khởi tạo ChromaDB đã được xử lý:
- `hybrid_retriever.py` ✓
- `vector_store.py` ✓
- `semantic_cache.py` ✓
- `rag_pipeline.py` ✓

**Pattern:**
```python
from pathlib import Path

path_obj = Path(persist_directory).resolve()
path_obj.mkdir(parents=True, exist_ok=True)
normalized_path = str(path_obj.as_posix())

client = chromadb.PersistentClient(path=normalized_path)
```

---

## 🎯 Luồng xử lý mới

### Ví dụ 1: DOMAIN_DATA
```
Q: "Môn Hệ thống nhúng có mấy tín chỉ?"
    ↓ (intent_node)
    → category = "DOMAIN_DATA"
    ↓ (route_after_intent)
    → retrieve_node (lấy từ ChromaDB)
    ↓
    → context_node (xây dựng context)
    ↓
    → answer_node (trả lời dựa trên context)
    ↓ (route_after_answer)
    → validation_node (kiểm tra có đầy đủ không)
    ↓
    → save_chat_node (lưu vào memory)

A: "Môn Hệ thống nhúng có 3 tín chỉ, mã môn: CSLS211, ..."
```

### Ví dụ 2: GENERAL_LLM
```
Q: "Dijkstra algorithm là gì?"
    ↓ (intent_node)
    → category = "GENERAL_LLM"
    ↓ (route_after_intent)
    → answer_node (trực tiếp, không retrieve)
    ↓ (route_after_answer)
    → save_chat_node (không validate)

A: "Dijkstra là thuật toán tìm đường đi ngắn nhất... [giải thích rõ ràng]"
```

---

## 🔧 Files được sửa

1. ✅ `src/prompts/intent_prompt.py` - System prompt mới (DOMAIN_DATA vs GENERAL_LLM)
2. ✅ `src/agent/nodes.py` - intent_node, answer_node, context_node
3. ✅ `src/agent/graph.py` - route_after_intent, route_after_answer
4. ✅ `src/agent/state.py` - Thêm `category` field
5. ✅ `src/rag/hybrid_retriever.py` - Xử lý Path Windows
6. ✅ `src/ingestion/vector_store.py` - Xử lý Path Windows
7. ✅ `src/cache/semantic_cache.py` - Xử lý Path Windows
8. ✅ `src/rag/rag_pipeline.py` - Xử lý Path Windows

---

## ✨ Lợi ích

| Trước | Sau |
|-------|-----|
| Generic intent list (9+) | 2 categories rõ ràng |
| Luôn gọi retrieve (slow) | GENERAL_LLM bỏ qua retrieve (fast) |
| Prompt generic cho cả RAG & LLM | Prompt chuyên biệt (Domain-specific vs General) |
| Validation cho mọi câu | Chỉ validate DOMAIN_DATA |
| ERROR 123 trên Windows | Xử lý Path với pathlib |

---

## 🧪 Test

### Test DOMAIN_DATA:
```
Q: "Giảng viên dạy môn Cơ sở dữ liệu là ai?"
Expected: category = "DOMAIN_DATA"
         → Gọi retrieve
         → Trả lời từ context

Q: "Kế hoạch giảng dạy của Hệ thống nhúng:"
Expected: category = "DOMAIN_DATA"
         → Retrieve + context
         → Trả lời chi tiết từng tuần
```

### Test GENERAL_LLM:
```
Q: "Dijkstra algorithm là gì?"
Expected: category = "GENERAL_LLM"
         → Skip retrieve
         → Trả lời từ LLM knowledge

Q: "Xin chào, bạn khỏe không?"
Expected: category = "GENERAL_LLM"
         → Skip retrieve
         → Chào hỏi thân thiện
```

---

## 📝 Notes

- Toàn bộ logic đã được kiểm tra exception handling
- Path Windows đã fix (Error 123)
- Singleton pattern cho ChromaDB client
- RAG chỉ gọi khi thực sự cần (cải thiện performance)
