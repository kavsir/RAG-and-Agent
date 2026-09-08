"""
Round C1 Regression Suite: Evidence Completeness & Multi-Value Extraction.
Reproduces and verifies real-user correctness fixes for:
- Case A: Lecturer extraction for FIT4201 (rejection of generic 'Thông tin giảng viên học', extraction of TS. Trần Đăng Công / ThS. Nguyễn Văn Nhân).
- Case B: CLO completeness for FIT4113 (all 8 CLOs extracted across chunks, 0 silent truncation).
- Case C: Multi-clause graduation requirements aggregation from regulation Điều 33.
"""
from src.agent_core.loop import AgentLoop
from src.agent_core.verifier import get_evidence_verifier
from src.agent_core.schemas import EvidenceRequirement, EvidenceStatus, FieldCardinality
from src.agent_core.cardinality import get_field_cardinality
from src.rag.hybrid_retriever import get_collection_retriever


class TestEvidenceCompletenessRoundC1:
    """Kiểm thử hồi quy cho tính trọn vẹn và tính đúng đắn của việc trích xuất đa giá trị."""

    def test_case_a_lecturer_extraction_not_generic_phrase(self):
        """Case A: Giảng viên môn Hệ thống nhúng (FIT4201) không được trả về cụm chung chung."""
        verifier = get_evidence_verifier()
        retriever = get_collection_retriever("course_detail")
        res = retriever.collection.get(where={"course_code": "FIT4201"})
        docs = [
            {
                "chunk_id": cid,
                "text": text,
                "content": text,
                "source_file": (meta or {}).get("source_file", "FIT4201- Hệ thống nhúng.docx"),
                "document_type": "course_detail",
            }
            for cid, meta, text in zip(res["ids"], res["metadatas"], res["documents"])
        ]

        req = EvidenceRequirement(entity="FIT4201", field="lecturer", accepted_document_types=["course_detail", "course_outline"])
        status, item = verifier.verify_requirement(req, docs, retrieval_strategy="exact")

        assert status == EvidenceStatus.VERIFIED_VALUE, f"Expected VERIFIED_VALUE, got {status}"
        assert item is not None, "EvidenceItem should not be None"
        content = item.content

        # Bắt buộc KHÔNG được chứa cụm từ rác bị trích sai
        assert "Thông tin giảng viên học" not in content, f"Erroneous generic phrase found: {content}"
        assert "thông tin giảng viên" not in content.lower(), f"Erroneous generic phrase found: {content}"

        # Bắt buộc chứa tên giảng viên thực tế trong đề cương FIT4201
        assert any(name in content for name in ["Trần Đăng Công", "Nguyễn Văn Nhân"]), (
            f"Expected real lecturer name (Trần Đăng Công / Nguyễn Văn Nhân), got: {content}"
        )

    def test_case_b_clo_completeness_all_eight(self):
        """Case B: Chuẩn đầu ra FIT4113 phải trích xuất đầy đủ 8 CLO (không bị cắt còn 3)."""
        verifier = get_evidence_verifier()
        retriever = get_collection_retriever("course_detail")
        res = retriever.collection.get(where={"course_code": "FIT4113"})
        docs = [
            {
                "chunk_id": cid,
                "text": text,
                "content": text,
                "source_file": (meta or {}).get("source_file", "FIT4113 - Công nghệ điện toán đám mây.docx"),
                "document_type": "course_detail",
            }
            for cid, meta, text in zip(res["ids"], res["metadatas"], res["documents"])
        ]

        req = EvidenceRequirement(entity="FIT4113", field="clo", accepted_document_types=["course_detail", "course_outline"])
        status, item = verifier.verify_requirement(req, docs, retrieval_strategy="exact")

        assert status == EvidenceStatus.VERIFIED_VALUE, f"Expected VERIFIED_VALUE, got {status}"
        assert item is not None, "EvidenceItem should not be None"
        content = item.content

        # Kiểm tra sự có mặt của tất cả 8 CLO
        for i in range(1, 9):
            clo_key = f"CLO {i}"
            clo_alt = f"CLO{i}"
            assert (clo_key in content or clo_alt in content), f"Missing {clo_key} in extracted CLOs: {content}"

        # Xác thực hỗ trợ đa chunk trong metadata provenance
        supporting = item.metadata.get("supporting_chunks", [])
        assert len(supporting) >= 1, "Expected supporting_chunks in metadata for multi-chunk CLO"

    def test_case_c_graduation_requirements_multi_clause(self):
        """Case C: Điều kiện xét tốt nghiệp phải tổng hợp đa điều khoản từ Điều 33 quy chế."""
        verifier = get_evidence_verifier()
        retriever = get_collection_retriever("regulation")
        # Tìm các chunk liên quan đến tốt nghiệp
        b_docs = retriever.bm25_search("điều kiện xét tốt nghiệp công nhận tốt nghiệp", top_k=5)
        docs = [
            {
                "chunk_id": d["id"],
                "text": d["text"],
                "content": d["text"],
                "source_file": "QuyetDinhChung.docx",
                "document_type": "regulation",
            }
            for d in b_docs
        ]

        req = EvidenceRequirement(entity="DNTU", field="graduation_requirements", accepted_document_types=["regulation"])
        status, item = verifier.verify_requirement(req, docs, retrieval_strategy="exact")

        assert status == EvidenceStatus.VERIFIED_VALUE, f"Expected VERIFIED_VALUE, got {status}"
        assert item is not None, "EvidenceItem should not be None"
        content = item.content.lower()

        # Phải chứa nhiều hơn 1 mệnh đề điều kiện
        clauses_checked = [
            any(k in content for k in ["tích lũy", "tín chỉ"]),
            any(k in content for k in ["chuẩn đầu ra", "ngoại ngữ"]),
            any(k in content for k in ["điểm trung bình", "tích lũy"]),
            any(k in content for k in ["rèn luyện", "đánh giá rèn luyện"]),
            any(k in content for k in ["giáo dục quốc phòng", "quốc phòng"]),
            any(k in content for k in ["hình sự", "kỷ luật", "đình chỉ"]),
        ]
        satisfied_clauses = sum(1 for c in clauses_checked if c)
        assert satisfied_clauses >= 3, (
            f"Expected at least 3 distinct graduation condition clauses, got {satisfied_clauses}. Content: {item.content}"
        )

    def test_field_cardinality_policy(self):
        """Kiểm tra chính sách phân loại lực lượng trường (Field Cardinality Policy)."""
        assert get_field_cardinality("credits") == FieldCardinality.SINGLE_VALUE
        assert get_field_cardinality("lecturer") == FieldCardinality.MULTI_VALUE
        assert get_field_cardinality("clo") == FieldCardinality.MULTI_VALUE
        assert get_field_cardinality("assessment") == FieldCardinality.MULTI_COMPONENT
        assert get_field_cardinality("graduation_requirements") == FieldCardinality.MULTI_CLAUSE

    def test_conversational_answer_presentation_format(self):
        """Kiểm tra định dạng câu trả lời hội thoại không chứa markdown thô '- **FIT4201 (giảng viên)**:'."""
        loop = AgentLoop()
        state = loop.run(query="Giảng viên dạy môn Hệ thống nhúng là ai?")
        assert state.status.value == "COMPLETED"
        assert not state.final_answer.startswith("- **FIT4201 (giảng viên)**:"), (
            f"UX should be natural conversational format, got: {state.final_answer}"
        )
        assert "FIT4201" in state.final_answer
        assert "Trần Đăng Công" in state.final_answer or "Nguyễn Văn Nhân" in state.final_answer
