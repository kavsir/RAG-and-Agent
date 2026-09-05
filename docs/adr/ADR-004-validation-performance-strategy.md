# ADR-004: Validation Performance Strategy & Streaming UX Architecture

- **Status**: PROPOSED
- **Date**: 2026-09-06
- **Author**: AI Architecture Team / Agentic RAG
- **Component**: `src/agent/nodes.py` (`grounded_answer_node`, `validation_node`), `src/api/routes.py`

---

## 1. Context (Bối Cảnh)

Theo Báo cáo Đo lường Hiệu năng Thực tế (**Performance Profiling Report**):
- Thời gian phản hồi trung bình cho một câu hỏi học vụ không có cache (**DOMAIN Cache Miss**) là **~12.19 giây** (P50: 10.06 giây).
- Trong đó, các cuộc gọi mạng đến Cloud LLM (`api.deepseek.com`) chiếm tới **> 99.3%** tổng độ trễ của hệ thống:
  - **Lượt 1 (Grounded Answer Generation)**: Chiếm ~3.4 giây (sinh nội dung).
  - **Lượt 2 (Factuality Guardrail Validation)**: Chiếm ~8.7 giây (kiểm tra toàn bộ ngữ cảnh và câu trả lời).
- Mặc dù bước Validation mất thời gian nhiều nhất, đây chính là **lá chắn cốt lõi** giúp hệ thống đạt thành tích:
  - **Critical Hallucinations = 0 ca**
  - **Abstention Accuracy = 100.0%**
  - **Wrong-Premise Resistance = 100.0%**

---

## 2. Core Invariant (Ràng Buộc An Toàn Tuyệt Đối)

> [!CAUTION]
> **QUY TẮC BẤT BIẾN**: Tuyệt đối **KHÔNG ĐƯỢC XÓA BỎ** bước kiểm định tính trung thực (Factuality Validation) chỉ vì mục tiêu giảm độ trễ.
> Mục tiêu tối thượng của sản phẩm là thông tin học vụ chuẩn xác 100% cho sinh viên. Mọi giải pháp tối ưu hóa hiệu năng phải bảo toàn nguyên vẹn 3 chỉ số an toàn vàng trên.

---

## 3. Options Considered (Các Phương Án Cân Nhắc)

### Phương án 1: Bỏ hoàn toàn bước Validation
- *Đánh giá*: **BÁC BỎ HOÀN TOÀN (STRICT REJECT)**. Mô hình ngôn ngữ lớn (kể cả GPT-4o hay DeepSeek V4) vẫn có xác suất sinh ảo giác hoặc đồng ý với câu hỏi bẫy nếu không có guardrail độc lập.

### Phương án 2: Kiểm định Bất đồng bộ trong Nền (Async Background Validation)
- *Mô tả*: Trả câu trả lời ngay cho người dùng, sau đó chạy kiểm định ngầm; nếu sai thì gửi thông báo đính chính.
- *Đánh giá*: **BÁC BỎ (REJECT)**. Sinh viên có thể đọc thông tin sai lệch trước khi thông báo đính chính xuất hiện, gây rủi ro học vụ nghiêm trọng (ví dụ nhầm lịch thi hoặc điều kiện tốt nghiệp).

### Phương án 3: Kiểm định Hợp nhất Đơn vòng (Single-Pass Chain-of-Thought Validation) — *ĐƯỢC CHỌN (P1)*
- *Mô tả*: Thay vì gọi 2 lượt HTTP riêng biệt tới máy chủ LLM (Lượt 1: Sinh câu trả lời &rarr; Lượt 2: Kiểm định), gộp chung vào 1 prompt duy nhất yêu cầu mô hình thực hiện đối chiếu factsheet trước trong suy luận (Chain-of-Thought / Structured JSON), sau đó mới xuất câu trả lời chính thức.
- *Cấu trúc Output kỳ vọng*:
  ```json
  {
    "fact_check": {
      "context_supports": true,
      "verified_facts": ["2 tín chỉ", "1 lý thuyết", "1 thực hành"],
      "hallucination_detected": false
    },
    "answer": "Theo đề cương chi tiết học phần FIT4201, môn học có 2 tín chỉ..."
  }
  ```
- *Lợi ích*: Giảm từ 2 lượt gọi mạng xuống còn **1 lượt duy nhất**, cắt giảm ngay **40% – 50% tổng độ trễ** (từ ~12s xuống ~6s) mà vẫn giữ nguyên logic kiểm định bám sát ngữ cảnh.

### Phương án 4: Phản hồi Dòng (Streaming Response via Server-Sent Events - SSE) — *ĐƯỢC CHỌN (P0)*
- *Mô tả*: Bổ sung giao thức streaming (`FastAPI StreamingResponse`) cho endpoint chat.
- *Lợi ích*: Giảm thời gian chờ đợi nhận diện đầu tiên (**Time-to-First-Token - TTFT**) của người dùng từ **10 giây xuống còn < 1.5 giây**. Sinh viên thấy câu trả lời xuất hiện ngay tức thì theo từng chữ, tạo trải nghiệm mượt mà và trực quan.

---

## 4. Decision Proposal (Đề Xuất Quyết Định)

1. **Giai đoạn 1 (UX Streaming)**:
   - Thêm chế độ streaming tại endpoint `POST /api/chat/stream`.
   - Client Web nhận từng chunk token qua EventSource / Fetch ReadableStream.
2. **Giai đoạn 2 (Single-Pass CoT Validation)**:
   - Thiết kế lại `GROUNDED_ANSWER_PROMPT` kết hợp kiểm định CoT và trả về cấu trúc JSON có kiểm định factsheet nội bộ.
   - Nếu `fact_check.hallucination_detected == true` hoặc `context_supports == false` &rarr; Cưỡng chế kích hoạt luồng từ chối an toàn (**Safe Abstention**).
3. **Giai đoạn 3 (Giới hạn Token Budget)**:
   - Cấu hình `max_tokens = 600` cho các câu hỏi học vụ định lượng (thay vì để mặc định không giới hạn). Tiết kiệm thêm 20% thời gian token generation của Cloud LLM.

---

## 5. Consequences & Risk Management (Hệ Quả & Quản Lý Rủi Ro)

- **Lợi ích**:
  - Giảm perceived latency cho sinh viên xuống dưới 1.5 giây (nhờ Streaming).
  - Giảm tổng thời gian xử lý hoàn tất xuống ~5 – 6 giây (nhờ Single-Pass Validation).
  - Tiết kiệm 50% chi phí API calls tới nhà cung cấp LLM.
- **Rủi ro chất lượng**:
  - Mô hình có thể "tự kiểm tra lỏng lẻo" hơn so với một prompt thẩm định riêng biệt.
  - *Biện pháp kiểm soát*: Chạy lại toàn bộ **Adversarial Benchmark V2 (62 cases)** sau khi đổi sang Single-Pass CoT. Nếu bất kỳ chỉ số nào trong 3 chỉ số an toàn (Critical Hallucinations, Abstention, Wrong Premise) giảm dưới 100% &rarr; Lập tức rollback về kiến trúc Two-Hop ban đầu.

---

## 6. Metrics to Validate

1. `Critical Hallucinations`: Bắt buộc giữ vững **0 ca**.
2. `Abstention Accuracy`: Bắt buộc giữ vững $\ge 95\%$ (hiện tại 100%).
3. `Wrong-Premise Resistance`: Bắt buộc giữ vững $\ge 95\%$ (hiện tại 100%).
4. `Time-to-First-Token (TTFT)`: Giảm từ **10.0s xuống < 1.5s**.
5. `Total DOMAIN Latency Mean`: Giảm từ **12.2s xuống < 7.0s**.
