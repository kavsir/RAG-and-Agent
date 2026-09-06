# AGENT CORE EVALUATION SUITE

Bộ kiểm thử tự động toàn diện dành cho phân hệ **Goal-Driven Agent Core V1**.

## 1. Cấu trúc thư mục

```
eval/agent_core/
├── datasets/
│   └── agent_core_cases.json   # 182 test cases qua 16 nhóm kiểm thử A - P
├── runner.py                   # Bộ thực thi đánh giá, đo lường Hard Gates & Quality Metrics
└── README.md                   # Tài liệu hướng dẫn sử dụng bộ kiểm thử
```

## 2. Danh mục 16 nhóm kiểm thử (Groups A - P)

1. **Group A (CLEAR_GOAL - 20 cases):** Mục tiêu rõ ràng (đơn thực thể, đa thực thể, đơn turn, multi-turn có session memory, quy chế).
2. **Group B (MISSING_INTENT - 12 cases):** Thiếu ý định tra cứu rõ ràng, kiểm tra khả năng hỏi lại.
3. **Group C (MISSING_ENTITY - 12 cases):** Thiếu thực thể học vụ mục tiêu khi session trống.
4. **Group D (MISSING_DATA - 14 cases):** Dữ liệu không công bố chính thức, kích hoạt đề xuất giải pháp thay thế.
5. **Group E (UNKNOWN_ENTITY - 12 cases):** Mã môn lạ, không tồn tại trong CTĐT, kiểm định từ chối an toàn 100%.
6. **Group F (ENTITY_CONFLICT - 10 cases):** Mâu thuẫn mã môn và tên môn, yêu cầu người dùng xác nhận.
7. **Group G (MULTI_FIELD - 12 cases):** Yêu cầu đa trường thông tin (tín chỉ, giảng viên, chuẩn đầu ra, đánh giá).
8. **Group H (MULTI_ENTITY - 12 cases):** So sánh giữa 2 hoặc nhiều học phần chính quy.
9. **Group I (PARTIAL_EVIDENCE - 10 cases):** Kết hợp giữa thông tin có sẵn và thông tin không công bố.
10. **Group J (NO_PROGRESS - 8 cases):** Kiểm tra cơ chế chống lặp khi không có tiến triển mới.
11. **Group K (DUPLICATE_ACTION - 8 cases):** Kiểm tra cơ chế ngăn chặn hành động trùng lặp qua ActionFingerprint.
12. **Group L (APPROVED_ALTERNATIVE - 10 cases):** Chu trình Human-in-the-loop khi người dùng đồng ý phương án thay thế.
13. **Group M (REJECTED_ALTERNATIVE - 8 cases):** Chu trình Human-in-the-loop khi người dùng từ chối phương án thay thế.
14. **Group N (CLARIFICATION_RESUME - 12 cases):** Khôi phục và hoàn tất mục tiêu sau khi nhận câu trả lời làm rõ.
15. **Group O (MALFORMED_QUERY - 12 cases):** Câu hỏi dị dạng, viết hoa, dấu câu bất thường, teencode.
16. **Group P (MULTI_INTENT - 10 cases):** Câu hỏi đa ý định (kết hợp tra cứu học vụ và yêu cầu công cụ).

## 3. Lệnh chạy kiểm thử

```powershell
python eval/agent_core/runner.py
```

Toàn bộ kết quả chi tiết được kết xuất tự động tại `eval/results/agent_core_eval.json`.
