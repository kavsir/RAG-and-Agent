# QUY CHẾ TƯƠNG TÁC HUMAN-IN-THE-LOOP (AGENT HUMAN-LOOP POLICY)

**Dự án:** AI Academic Advisor / Agentic RAG  
**Phân hệ:** Human-in-the-loop Orchestrator (`src/agent_core/loop.py`, `src/agent_core/service.py`)

---

## 1. NGUYÊN TẮC THIẾT KẾ: ASK_USER LÀ MỘT FIRST-CLASS CITIZEN

Trong Agent Core V1, việc đặt câu hỏi lại cho người dùng (`ASK_USER`) không phải là biểu hiện của lỗi, mà là **một hành động có chủ đích và có giá trị cao nhất** khi:
- Mục tiêu người dùng chưa đủ rõ ràng.
- Thiếu thông tin thực thể cần thiết.
- Phát hiện mâu thuẫn giữa mã môn học và tên môn học.
- Dữ liệu người dùng yêu cầu không có sẵn trong tài liệu chính thức và cần người dùng đồng ý trước khi chuyển sang phương án phân tích gián tiếp.

---

## 2. CÁC DẠNG CÂU HỎI LÀM RÕ (CLARIFICATION MODES)

### 2.1. Làm rõ ý định bị thiếu (`MISSING_INTENT`)
- **Tình huống kích hoạt:** Người dùng cung cấp mã môn học nhưng không chỉ rõ muốn tra cứu điều gì (ví dụ: *"FIT4201 với FIT4104 thì sao?"*).
- **Hành vi Agent:**
  - Xác định các thực thể đã biết (`FIT4201`, `FIT4104`).
  - Đưa ra câu hỏi định hướng kèm các tùy chọn tiêu chí tra cứu:
    `"Bạn muốn mình so sánh FIT4201 và FIT4104 theo tiêu chí nào (số tín chỉ, giảng viên, chuẩn đầu ra hay hình thức đánh giá)?"`
  - Chuyển trạng thái sang `NEEDS_USER_INPUT` và lưu giữ `goal_id`.

### 2.2. Bổ sung thực thể bị thiếu (`MISSING_ENTITY`)
- **Tình huống kích hoạt:** Người dùng hỏi về một thuộc tính học vụ cụ thể nhưng không chỉ rõ môn học và session không có môn hoạt động (ví dụ: *"Môn đó bao nhiêu tín chỉ?"*).
- **Hành vi Agent:**
  - Nhận diện trường thông tin yêu cầu (`credits`).
  - Hỏi người dùng cung cấp mã môn hoặc tên môn học:
    `"Bạn đang hỏi về môn học / học phần nào? Bạn có thể cung cấp mã môn học hoặc mã học phần (ví dụ FIT4201) để mình tra cứu chính xác nhé."`

### 2.3. Giải quyết mâu thuẫn thực thể (`ENTITY_CONFLICT`)
- **Tình huống kích hoạt:** Người dùng viết mã môn A kèm theo tên gọi của môn B (ví dụ: *"FIT4201 môn Full-Stack bao nhiêu tín chỉ?"*).
- **Hành vi Agent:**
  - Nhận diện `FIT4201` là môn "Hệ thống nhúng", còn "Full-Stack" là môn `FIT4104`.
  - Đặt câu hỏi làm rõ để người dùng xác nhận môn học chính xác:
    `"Bạn đang muốn hỏi về môn FIT4201 (Hệ thống nhúng) hay học phần FIT4104 (Dự án thiết kế, lập trình Full-Stack)?"`

### 2.4. Đề xuất phương án thay thế (`MISSING_DATA_ALTERNATIVE`)
- **Tình huống kích hoạt:** Người dùng hỏi về tỷ lệ trượt môn, độ khó, review sinh viên, mức lương hoặc lộ đề thi.
- **Hành vi Agent:**
  - Giải thích lý do tài liệu chính thức không công bố chỉ số này.
  - Đề xuất các tiêu chí chính quy thay thế (số tín chỉ, số giờ thực hành, cấu trúc điểm).
  - Đưa ra 2 lựa chọn rõ ràng: Đồng ý phân tích theo tiêu chí thay thế hoặc Dừng tra cứu.

---

## 3. CƠ CHẾ KHÔI PHỤC VÀ DUY TRÌ TRẠNG THÁI (RESUMPTION POLICY)

Khi người dùng phản hồi câu hỏi làm rõ:
1. Hệ thống tìm nạp phiên mục tiêu thông qua `service.resume_goal(goal_id, user_response)`.
2. **Không tạo mới GoalSpec từ đầu**: Tác tử kế thừa toàn bộ lịch sử và bối cảnh đã thu thập được từ bước trước.
3. **Cập nhật có mục tiêu**:
   - Nếu người dùng đồng ý phương án thay thế: Cập nhật `state.alternative_authorized = True`, thay thế các requirement không khả dụng bằng các requirement thay thế hợp lệ và tiếp tục vòng lặp.
   - Nếu người dùng từ chối: Chuyển ngay sang `state.status = AgentStatus.ABSTAINED` với phản hồi ghi nhận lịch sự, không tra cứu tiếp.
   - Nếu người dùng bổ sung mã môn: Cập nhật `state.entities`, giữ nguyên các trường yêu cầu ban đầu và tiến hành tra cứu.
