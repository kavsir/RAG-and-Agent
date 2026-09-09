# BÁO CÁO ROUND A1.2: REMOVE SILENT RESULT TRUNCATION
**Hợp đồng Lực lượng Kết quả Tri thức Học vụ (Result Cardinality Contract)**

---

## 1. TỔNG QUAN & LỖI SẢN XUẤT ĐÃ LOẠI BỎ

### 1.1 Khuyết tật sản xuất (Confirmed Production Defect)
Trước Round A1.2, tầng hiển thị (`src/agent_core/presentation.py`) tồn tại đoạn mã cắt ngắn cứng số lượng học phần hiển thị:
```python
for c in courses[:25]:
    ...
if len(courses) > 25:
    lines.append(f"\n*(Hiển thị 25/{len(courses)} học phần. Bạn có thể hỏi chi tiết từng kỳ...)*")
```
và hàm `list_curriculum_courses` tại `src/agent_core/academic_store.py` có tham số mặc định `limit: int = 200`.

Hành vi này tước đoạt quyền nhận dữ liệu đầy đủ của người dùng, vi phạm nguyên tắc thẩm quyền mục tiêu người dùng (*User Goal Authority*) khi sinh viên yêu cầu xem toàn bộ chương trình đào tạo.

### 1.2 Nguyên tắc khắc phục
- **KHÔNG** nâng số 25 lên 57, 100 hay bất kỳ hằng số nào khác.
- Tước bỏ hoàn toàn quyền năng quyết định lực lượng kết quả của tầng Presentation (`PRESENTATION_CARDINALITY_OVERRIDE = 0`).
- Thiết lập hợp đồng lực lượng có kiểu (*Result Cardinality Contract*) xuyên suốt toàn bộ luồng xử lý:
  $$\text{User Scope Cue} \rightarrow \text{GoalFrame} \rightarrow \text{AcademicQueryPlan} \rightarrow \text{StructuredAcademicStore} \rightarrow \text{AcademicCollectionResult} \rightarrow \text{Presentation}$$

---

## 2. KIẾN TRÚC KẾT QUẢ CÓ LỰC LƯỢNG (CARDINALITY ARCHITECTURE)

### 2.1 Định nghĩa `ResultScope` và `AcademicCollectionResult` (`src/agent_core/schemas.py`)
```python
class ResultScope(str, Enum):
    SUMMARY = "SUMMARY"
    PAGE = "PAGE"
    TOP_K = "TOP_K"
    ALL = "ALL"

class AcademicCollectionResult(BaseModel):
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    returned_count: int = 0
    is_complete: bool = True
    truncation_reason: Optional[str] = None
    result_scope: ResultScope = ResultScope.ALL
    page: Optional[int] = None
    limit: Optional[int] = None

    def model_post_init(self, __context: Any) -> None:
        if self.result_scope == ResultScope.ALL:
            if self.total_count > 0 and self.returned_count != self.total_count:
                raise ValueError(
                    f"ALL_SCOPE_INCOMPLETE_RESULT: ResultScope.ALL requires returned_count ({self.returned_count}) == total_count ({self.total_count})"
                )
            self.is_complete = True
            self.truncation_reason = None
        elif self.returned_count < self.total_count:
            self.is_complete = False
```

### 2.2 Thẩm quyền Mục tiêu Người dùng (`src/agent_core/semantic_goal_interpreter.py`)
Hệ thống giải nghĩa tín hiệu số lượng tường minh từ câu hỏi:
- **`ALL`**: Khi người dùng dùng các từ khóa như *"tất cả"*, *"toàn bộ"*, *"hết"*, *"đầy đủ"*, *"full"* hoặc truy vấn danh sách chương trình mặc định.
- **`TOP_K`**: Khi người dùng yêu cầu số lượng cụ thể (ví dụ: *"10 môn đầu"*, *"top 5"*).
- **`PAGE`**: Khi người dùng yêu cầu phân trang (ví dụ: *"trang 2"*, *"trang tiếp theo"*).
- **`SUMMARY`**: Khi người dùng yêu cầu tóm tắt ngắn (ví dụ: *"tổng quan ngắn"*, *"ngắn gọn"*, *"sơ lược"*).

### 2.3 Phòng vệ Kế hoạch Truy vấn (`src/agent_core/query_planner.py`)
Thêm kiểm tra tính nhất quán 5 trong `GoalPlanConsistencyValidator`:
- Khi `GoalFrame.result_scope == ResultScope.ALL`, kế hoạch truy vấn `AcademicQueryPlan` tuyệt đối không được phép bị hạ cấp.
- Cơ chế tự chữa lành (*self-healing*) tự động khôi phục `plan.result_scope = ResultScope.ALL` và loại bỏ `limit` nếu phát hiện lỗi vi phạm.

### 2.4 Truy vấn Kho Học vụ Có Cấu trúc (`src/agent_core/academic_store.py`)
- `list_curriculum_courses`: Đổi tham số `limit: Optional[int] = None`. Khi `limit is None`, loại bỏ hoàn toàn mệnh đề SQL `LIMIT ?`.
- `get_curriculum_collection`: Thực hiện đếm chính xác `total_count` và chỉ áp dụng `LIMIT / OFFSET` khi `result_scope` là `TOP_K`, `PAGE`, hoặc `SUMMARY`. Với `ResultScope.ALL`, truy vấn trả về 100% bản ghi.

### 2.5 Định dạng Tầng Hiển thị (`src/agent_core/presentation.py`)
- `format_curriculum_overview`: Loại bỏ hoàn toàn `courses[:25]`. Duyệt qua và hiển thị toàn bộ `items` có trong hợp đồng.
- Ghi chú giới hạn chỉ xuất hiện khi `not is_complete and returned_count < total_count` (do người dùng chủ đích yêu cầu `TOP_K` hoặc `PAGE`).

---

## 3. CHỨNG NHẬN BỐN CỔNG CHẶN BẤT BIẾN (FOUR HARD GATES CERTIFICATION)

| STT | Cổng chặn (Hard Gate) | Điều kiện kiểm định | Kết quả | Trạng thái |
| :---: | :--- | :--- | :---: | :---: |
| 1 | **`SILENT_RESULT_TRUNCATION = 0`** | CNTT K19: 66/66 học phần; KHMT K19: 66/66 học phần được trả về trọn vẹn | 0 lỗi | **PASSED** |
| 2 | **`ALL_SCOPE_INCOMPLETE_RESULT = 0`** | `AcademicCollectionResult` lập tức raise `ValueError` nếu phạm vi `ALL` bị thiếu bản ghi | 0 vi phạm | **PASSED** |
| 3 | **`PRESENTATION_CARDINALITY_OVERRIDE = 0`** | Bảng Markdown hiển thị chính xác 66 hàng cho 66 học phần, không tự ý cắt ngắn | 0 dòng bị cắt | **PASSED** |
| 4 | **`USER_SCOPE_LOST_IN_PIPELINE = 0`** | Validator phát hiện và ngăn chặn hạ cấp phạm vi `ALL` từ Goal sang Plan | 0 rò rỉ | **PASSED** |

---

## 4. VẾT THỰC THI SẢN XUẤT (PRODUCTION QUERY TRACE)

### Truy vấn mẫu: `"hiển thị tất cả học phần của CNTT"`
Kết quả kiểm thử đầu-cuối:
```text
[GOAL] scope=ALL
[PLAN] scope=ALL
[STORE] total=66, returned=66, is_complete=True
[EXECUTOR] state.status=COMPLETED
[PRESENTATION] table_rows=66
VERDICT: RESULT_CARDINALITY_CONTRACT_ACCEPTED
```

---

## 5. KẾT LUẬN & CAM KẾT VẬN HÀNH

Toàn bộ 7 kiểm thử chuyên biệt tại `tests/unit/test_result_cardinality.py` và 24 kiểm thử hồi quy học vụ đều vượt qua 100%. Hệ thống chính thức bảo đảm tính minh bạch và toàn vẹn lực lượng kết quả theo hợp đồng tri thức học vụ chuẩn.
