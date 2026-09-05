# ADR-003: Retrieval Speed Optimization — Exact Entity Fast Path & Embedding Cache

- **Status**: PROPOSED
- **Date**: 2026-09-06
- **Author**: AI Architecture Team / Agentic RAG
- **Component**: `src/rag/hybrid_retriever.py`, `src/ingestion/vector_store.py`

---

## 1. Context (Bối Cảnh)

Hồ sơ đo lường hiệu năng thực tế (**Performance Profiling Report**) ghi nhận:
- Toàn bộ chuỗi xử lý RAG cục bộ (Local Pipeline) mất trung bình **~81.67 ms**.
- Trong đó, **Dense Vector Search** chiếm **75.82 ms (92.8%)** tổng thời gian local, do phải tính toán vector embedding 1024 chiều bằng mô hình transformer `BAAI/bge-m3` trên CPU máy tính cá nhân.
- Ngược lại, **BM25 Sparse Search** chỉ mất **0.94 ms (1.2%)**, và **Context Builder** chỉ mất **0.61 ms (0.7%)**.
- Độ chính xác tìm kiếm hiện tại đạt mức gần như tuyệt đối: **Recall@5 = 100.0%**, **Recall@20 = 100.0%**, **MRR = 0.9399**.

Mục tiêu là tối ưu hóa tốc độ truy xuất cục bộ mà **tuyệt đối không làm suy giảm các chỉ số chất lượng vàng (Recall@5 & MRR)**.

---

## 2. Options Considered & Classification (Các Phương Án & Phân Loại)

| Phương Án Đề Xuất | Phân Loại Can Thiệp | Khả Năng Giảm Latency | Nguy Cơ Giảm Chất Lượng | Quyết Định Đánh Giá |
| :--- | :--- | :---: | :---: | :--- |
| **A. Exact Entity Fast Path** | **ARCHITECTURE** | Giảm ~70 ms (xuống < 5ms) | 0% (Dữ liệu chính xác 100%) | ✅ **ĐỀ XUẤT ÁP DỤNG (P1)** |
| **B. Query Embedding Cache** | **ARCHITECTURE** | Giảm ~75 ms cho query lặp | 0% (Cache vector toán học) | ✅ **ĐỀ XUẤT ÁP DỤNG (P1)** |
| **C. Metadata Pre-filter** | **ALGORITHM_POLICY** | Đã triển khai | 0% | ℹ️ **ĐÃ CÓ TRONG HỆ THỐNG** |
| **D. Collection Routing** | **ALGORITHM_POLICY** | Đã triển khai | 0% | ℹ️ **ĐÃ CÓ TRONG HỆ THỐNG** |
| **E. Thay model nhỏ hơn MiniLM** | **MODEL_CHOICE** | Giảm ~40 ms | **RẤT CAO** (Mất Recall tiếng Việt) | ❌ **BÁC BỎ (REJECT)** |
| **F. Adaptive Candidates (20 &rarr; 12)** | **PARAMETER_CONFIG** | Giảm ~5 ms | Thấp nếu có filter mạnh | 🔍 **ĐƯA VÀO PARAMETER SWEEP** |
| **G. Tinh chỉnh RRF_K (60 &rarr; 40)** | **PARAMETER_CONFIG** | 0 ms (chỉ ảnh hưởng rank) | Cần kiểm chứng benchmark | 🔍 **ĐƯA VÀO PARAMETER SWEEP** |

---

## 3. Detailed Architecture Decisions (Chi Tiết Kiến Trúc Đề Xuất)

### Decision 1: Lối Đi Tắt Thực Thể Xác Thực (Exact Entity Fast Index Path)
- **Bản chất**: Khoảng 60% các câu hỏi của sinh viên chứa mã môn học cụ thể (ví dụ: `FIT4201`, `FIT4104`, `FIT4117`).
- **Cơ chế**:
  1. Khi `QueryAnalyzer` phát hiện một mã môn hợp lệ đã được định danh trong cơ sở dữ liệu `course_detail`:
  2. Bỏ qua bước mã hóa dense vector qua CPU (`bge-m3.encode()`), thay vào đó trực tiếp truy vấn nhanh các chunk tài liệu theo index `course_code` đã lưu sẵn trong ChromaDB / In-memory dictionary.
  3. Lọc theo `targets` (ví dụ: nếu hỏi về giảng viên, lấy ngay các chunks có `section="Mục II"` hoặc chứa `"thông tin giảng viên"`).
  4. Nếu số lượng chunks tìm thấy đủ tin cậy ($\ge 3$ chunks có độ khớp target cao) &rarr; Chuyển thẳng sang `Context Builder`.
  5. Nếu không đủ tin cậy hoặc câu hỏi mơ hồ &rarr; Fallback về chuỗi `Dense + BM25 + RRF` bình thường.
- **Hiệu quả kỳ vọng**: Thời gian truy xuất giảm từ **~80 ms xuống < 5 ms** đối với hơn một nửa tổng số câu hỏi học vụ.

### Decision 2: Bộ Đệm Vector Embedding Truy Vấn (Query Embedding Cache)
- **Bản chất**: Nhiều câu hỏi có cấu trúc câu tương tự nhau (ví dụ: *"FIT4201 có bao nhiêu tín chỉ?"*, *"Môn FIT4201 mấy tín chỉ?"*).
- **Cơ chế**:
  - Tạo một `LRUCache` kích thước 1,000 mục, lưu trữ cặp `normalized_query_string -> embedding_vector (1024-float array)`.
  - Khi gặp câu hỏi đã từng tính toán vector trong phiên làm việc, lấy vector trực tiếp trong 0.01 ms thay vì chạy forward-pass PyTorch 75 ms.
- **Tiêu thụ RAM**: 1,000 vectors $\times 1024 \times 4$ bytes $\approx 4$ MB (hoàn toàn không ảnh hưởng đến bộ nhớ RAM laptop).

### Decision 3: Bác Bỏ Việc Đổi Mô Hình Embedding Sang Loại Nhỏ Hơn
- Mô hình `BAAI/bge-m3` tuy nặng khi khởi động (Cold start ~27s) nhưng mang lại chất lượng tìm kiếm ngữ nghĩa tiếng Việt vượt trội (**Recall@5 đạt 100.0%**).
- Việc hạ cấp xuống mô hình nhỏ hơn (như MiniLM hoặc Paraphrase-multilingual) có rủi ro rất cao làm gãy các câu hỏi không chứa mã môn (`NO_CODE`) hoặc câu có lỗi chính tả (`TYPO_NOISY`).
- Do đó: **Giữ nguyên BAAI/bge-m3**, tối ưu bằng Fast Index và Caching thay vì đổi model.

---

## 4. Target Retrieval Flow (Sơ Đồ Luồng Truy Xuất Đích)

```
Câu hỏi người dùng
       │
       ▼
[Query Analyzer]
       │
   Có mã môn chính xác?
   ├── YES ──► [Exact Entity Fast Index] ──(Đủ chunk & target khớp)──► [Context Builder] (<5ms)
   │                    │
   │               (Không đủ)
   └── NO ──────────────┼──────────────►
                        │
                        ▼
            [Query Embedding Cache]
               ├── (Hit) ──► Vector có sẵn (<0.1ms)
               └── (Miss) ──► Chạy bge-m3 encode (~75ms)
                        │
                        ▼
            [Collection Router]
                        │
                        ▼
       [Dense Search] + [BM25 Search]
                        │
                        ▼
            [Reciprocal Rank Fusion (RRF)]
                        │
                        ▼
               [Context Builder]
```

---

## 5. Invariants & Risk Assessment (Ràng Buộc & Rủi Ro)

- **Bất biến**:
  - `Source Recall@5` $\ge 95\%$ (Mục tiêu giữ nguyên 100%).
  - `MRR` $\ge 0.90$.
- **Rủi ro**:
  - Nếu Fast Index lọc quá chặt, có thể bỏ sót thông tin liên môn.
  - *Biện pháp giảm thiểu*: Chỉ kích hoạt Fast Index khi query có `course_code` cụ thể và luôn có cơ chế fallback về Hybrid Search nếu candidate dưới ngưỡng an toàn.
