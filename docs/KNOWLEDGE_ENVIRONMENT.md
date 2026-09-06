# TÀI LIỆU KHÔNG GIAN TRI THỨC HỌC VỤ (KNOWLEDGE ENVIRONMENT)

**Dự án:** AI Academic Advisor / Agentic RAG  
**Phân hệ:** Knowledge Environment Catalog (`src/agent_core/environment_catalog.py`)

---

## 1. PHÂN CẤP THẨM QUYỀN TÀI LIỆU (AUTHORITY HIERARCHY)

Hệ thống phân cấp thẩm quyền tài liệu theo nguyên tắc: Tài liệu chuyên biệt cấp học phần có thẩm quyền cao nhất về chi tiết môn học; tài liệu chương trình đào tạo có thẩm quyền cao nhất về vị trí môn học trong khung đào tạo; tài liệu quy chế có thẩm quyền cao nhất về các chế độ học vụ toàn trường.

| Cấp thẩm quyền | Loại tài liệu | Thư mục lưu trữ thực tế | Trách nhiệm thẩm quyền |
| :--- | :--- | :--- | :--- |
| **PRIMARY_COURSE_AUTHORITY** | Đề cương chi tiết học phần (`course_outline`) | `data_raw/course_detail/*.docx` | Thẩm quyền tuyệt đối về: Chuẩn đầu ra (CLO), hình thức đánh giá & thi, tỷ trọng điểm, giảng viên phụ trách, email giảng viên, số giờ lý thuyết/thực hành, học phần tiên quyết. |
| **PRIMARY_CURRICULUM_AUTHORITY** | Khung chương trình đào tạo K19 (`curriculum`) | `data_raw/curriculum/*.docx` | Thẩm quyền tuyệt đối về: Danh mục 63 mã học phần chính thức, tên môn học chuẩn, số tín chỉ, học kỳ dự kiến trong lộ trình, phân bổ khối kiến thức. |
| **PRIMARY_REGULATION_AUTHORITY** | Quy chế đào tạo chính quy (`regulation`) | `data_raw/regulation/QuyetDinhChung.docx` | Thẩm quyền tuyệt đối về: Quy định điểm chuyên cần tối đa, điều kiện xét tốt nghiệp, xử lý học vụ, cảnh báo học vụ, thang điểm đánh giá, học lại và cải thiện. |

---

## 2. BẢN ĐỒ ÁNH XẠ TRƯỜNG DỮ LIỆU CÓ THỂ XÁC MINH (VERIFIABLE FIELDS)

Hệ thống định nghĩa tường minh 26 trường thông tin được bảo trợ bởi các văn bản chính quy:

1. `course_code`: Mã học phần chuẩn hóa (ví dụ: `FIT4201`, `FIT4104`).
2. `course_name`: Tên học phần tiếng Việt.
3. `english_name`: Tên học phần tiếng Anh.
4. `credits`: Số tín chỉ học phần (2 - 4 tín chỉ).
5. `theory_hours`: Số giờ lý thuyết.
6. `practice_hours`: Số giờ thực hành, bài tập, thảo luận.
7. `hours`: Tổng hợp phân bổ số giờ học.
8. `department`: Khoa / Bộ môn phụ trách giảng dạy (Khoa CNTT).
9. `prerequisites`: Điều kiện học phần tiên quyết / học phần học trước.
10. `course_objective`: Mục tiêu tổng quát của học phần.
11. `objectives`: Chi tiết mục tiêu môn học.
12. `clo`: Chuẩn đầu ra học phần (Course Learning Outcomes: CLO1, CLO2, CLO3...).
13. `assessment`: Cơ cấu đánh giá học phần (Chuyên cần: 10%, Giữa kỳ: 40%, Thi kết thúc: 50%).
14. `course_plan`: Kế hoạch giảng dạy theo tuần/buổi học.
15. `lecturer`: Họ tên và học hàm/học vị của giảng viên phụ trách.
16. `lecturer_email`: Email chính thức của giảng viên (`@dainam.edu.vn`).
17. `semester`: Học kỳ phân bổ theo khung chương trình.
18. `course_placement`: Vị trí học phần trong tiến trình đào tạo.
19. `curriculum_structure`: Cấu trúc khối kiến thức (đại cương, cơ sở ngành, chuyên ngành).
20. `cohort_plan`: Kế hoạch đào tạo theo khóa (Khóa 19).
21. `total_credits_program`: Tổng số tín chỉ của toàn khóa học.
22. `graduation_requirements`: Điều kiện xét và công nhận tốt nghiệp.
23. `academic_warning`: Quy định cảnh báo học vụ và buộc thôi học.
24. `training_rules`: Quy chế tổ chức đào tạo theo hệ thống tín chỉ.
25. `grading_scale`: Thang điểm đánh giá (thang điểm 10, thang điểm 4, thang điểm chữ).
26. `attendance_rules`: Quy định điểm danh và điều kiện dự thi kết thúc học phần.

---

## 3. DANH MỤC TRƯỜNG DỮ LIỆU KHÔNG CÔNG BỐ (UNAVAILABLE FIELDS)

Hệ thống nhận diện chủ động 5 nhóm dữ liệu **hoàn toàn không tồn tại** trong các văn bản đào tạo chính quy của Nhà trường:

### 1. `failure_rate` (Tỷ lệ trượt môn / Thống kê rớt môn)
- **Lý do:** Nhà trường không công bố số liệu thống kê trượt/đỗ công khai trong đề cương.
- **Phương án thay thế đề xuất:** Phân tích cấu trúc điểm đánh giá, khối lượng tín chỉ và số giờ thực hành để ước lượng mức độ đòi hỏi.

### 2. `difficulty` (Chỉ số độ khó môn học)
- **Lý do:** Khái niệm "độ khó" là cảm nhận chủ quan của từng sinh viên, không phải chỉ số học vụ chính quy.
- **Phương án thay thế đề xuất:** So sánh gián tiếp qua số tín chỉ, tỷ trọng giờ thực hành và hình thức thi cuối kỳ.

### 3. `student_rating` (Review / Đánh giá chủ quan của sinh viên khóa trước)
- **Lý do:** Hệ thống chỉ cung cấp dữ liệu chính thống từ Nhà trường, không tích hợp diễn đàn review sinh viên.
- **Phương án thay thế đề xuất:** Cung cấp mục tiêu môn học, chuẩn đầu ra (CLO) và tiêu chí đánh giá chính thức.

### 4. `job_salary` (Mức lương sau tốt nghiệp)
- **Lý do:** Khung chương trình đào tạo không cam kết hoặc thống kê mức thu nhập cố định sau khi ra trường.
- **Phương án thay thế đề xuất:** Cung cấp định hướng nghề nghiệp, vị trí việc làm và chuẩn đầu ra kiến thức/kỹ năng của ngành học.

### 5. `exam_leak` (Đề thi các năm trước / Thông tin lộ đề thi)
- **Lý do:** Quy định bảo mật đề thi nghiêm ngặt của Nhà trường.
- **Phương án thay thế đề xuất:** Cung cấp hình thức thi chính thức (tự luận, bài tập lớn, thuyết trình) và tỷ trọng điểm số.
