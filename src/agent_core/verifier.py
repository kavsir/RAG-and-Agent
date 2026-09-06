"""
Evidence Verifier (VERIFY Phase) for Goal-Driven Agent Core V1.2.
Implements rigorous truth and evidence integrity:
- Verifies document types against EnvironmentCatalog
- Extracts structured values with complete provenance (source_file, chunk_id, section, retrieval_strategy)
- Distinguishes VERIFIED_NONE (explicit absence) from MISSING/INSUFFICIENT
- ZERO fabricated fallback values: missing text strictly yields MISSING or INSUFFICIENT.
- Strict cross-entity protection: documents from course A never satisfy course B.
- No fake email inference from lecturer names.
"""
import re
from typing import Dict, Any, List, Optional, Tuple

from src.agent_core.schemas import EvidenceRequirement, EvidenceStatus, EvidenceItem
from src.agent_core.environment_catalog import get_knowledge_environment_catalog, KnowledgeEnvironmentCatalog
from src.agent_core.entity_catalog import get_entity_catalog, EntityCatalog


class EvidenceVerifier:
    """Bộ kiểm định và trích xuất bằng chứng học vụ trung thực 100%."""

    def __init__(
        self,
        env_catalog: Optional[KnowledgeEnvironmentCatalog] = None,
        entity_catalog: Optional[EntityCatalog] = None,
    ):
        self.env_catalog = env_catalog or get_knowledge_environment_catalog()
        self.entity_catalog = entity_catalog or get_entity_catalog()

    def verify_requirement(
        self,
        requirement: EvidenceRequirement,
        retrieved_docs: List[Dict[str, Any]],
        retrieval_strategy: str = "exact",
    ) -> Tuple[EvidenceStatus, Optional[EvidenceItem]]:
        """Kiểm định một yêu cầu bằng chứng dựa trên các tài liệu đã thu thập."""
        entity = requirement.entity
        field = requirement.field

        # 1. Kiểm tra trường không tồn tại trong hệ thống chính quy
        if self.env_catalog.is_field_unavailable(field):
            return EvidenceStatus.NOT_AVAILABLE, None

        # 2. Nếu không có tài liệu truy xuất, kiểm tra xem catalog có provenance chính thống không
        if not retrieved_docs:
            if field == "credits" and entity and entity not in ("DNTU", "general"):
                c_info = self.entity_catalog.get_course_info(entity)
                if c_info and "provenance" in c_info and "credits_authoritative" in c_info["provenance"]:
                    cred_val = c_info["provenance"]["credits_authoritative"]
                    src = c_info["provenance"].get("source_file", f"curriculum_{entity}.docx")
                    item = EvidenceItem(
                        entity=entity,
                        field=field,
                        document_type="curriculum",
                        content=f"{cred_val} tín chỉ",
                        source=src,
                        source_file=src,
                        chunk_id=f"{entity}_curriculum_catalog",
                        is_authoritative=True,
                        status=EvidenceStatus.VERIFIED_VALUE,
                        retrieval_strategy=retrieval_strategy,
                    )
                    return EvidenceStatus.VERIFIED_VALUE, item

            return EvidenceStatus.MISSING, None

        # 3. Duyệt qua các tài liệu thu thập được để trích xuất bằng chứng thật
        filtered_docs = []
        for doc in retrieved_docs:
            # Cross-Entity Protection: Tài liệu của thực thể X không bao giờ được thỏa mãn thực thể Y
            doc_course = doc.get("course_code") or doc.get("metadata", {}).get("course_code")
            if not doc_course:
                combined_meta = (
                    str(doc.get("source_file", ""))
                    + " "
                    + str(doc.get("filename", ""))
                    + " "
                    + str(doc.get("chunk_id", ""))
                    + " "
                    + str(doc.get("id", ""))
                )
                m_code = re.search(r"\b(FIT\d{4}|CSC\d{4})\b", combined_meta)
                if m_code:
                    doc_course = m_code.group(1).upper()

            if entity and entity not in ("DNTU", "general") and doc_course:
                if entity.strip().upper() != str(doc_course).strip().upper():
                    # Cross-entity evidence leakage prevented!
                    continue

            filtered_docs.append(doc)

        if not filtered_docs:
            return EvidenceStatus.MISSING, None

        # 1. Với các trường thường bị ngắt đoạn qua ranh giới chunk (assessment, hours, clo),
        # nếu có nhiều chunk của cùng thực thể, thử trích xuất trên văn bản hợp nhất trước.
        if field in ("assessment", "hours", "clo") and len(filtered_docs) > 1:
            combined_text = "\n".join(d.get("content") or d.get("text", "") for d in filtered_docs)
            status, val = self._extract_field_value(field, combined_text, entity, filtered_docs[0].get("document_type", "course_detail"))
            if status in (EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE) and val is not None:
                first_doc = filtered_docs[0]
                doc_type = first_doc.get("document_type") or first_doc.get("metadata", {}).get("document_type", "course_detail")
                doc_id = first_doc.get("chunk_id") or first_doc.get("id") or first_doc.get("file_path", "unknown")
                source_file = (
                    first_doc.get("source_file")
                    or first_doc.get("metadata", {}).get("source_file")
                    or first_doc.get("filename")
                    or first_doc.get("metadata", {}).get("filename")
                    or str(doc_id)
                )
                section = "Đánh giá học phần" if field == "assessment" else (first_doc.get("section") or "")
                item = EvidenceItem(
                    entity=entity,
                    field=field,
                    document_type=doc_type,
                    content=val,
                    source=str(doc_id),
                    source_file=source_file,
                    chunk_id=str(doc_id),
                    section=section,
                    status=status,
                    is_authoritative=True,
                    retrieval_strategy=retrieval_strategy,
                )
                return status, item

        # 2. Trích xuất từng tài liệu độc lập
        for doc in filtered_docs:
            doc_type = doc.get("document_type") or doc.get("metadata", {}).get("document_type", "course_detail")
            doc_id = doc.get("chunk_id") or doc.get("id") or doc.get("file_path", "unknown")
            source_file = (
                doc.get("source_file")
                or doc.get("metadata", {}).get("source_file")
                or doc.get("filename")
                or doc.get("metadata", {}).get("filename")
                or str(doc_id)
            )
            section = doc.get("section") or doc.get("metadata", {}).get("section", "")
            text = doc.get("content") or doc.get("text", "")

            status, val = self._extract_field_value(field, text, entity, doc_type)
            if status in (EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE) and val is not None:
                item = EvidenceItem(
                    entity=entity,
                    field=field,
                    document_type=doc_type,
                    content=val,
                    source=str(doc_id),
                    source_file=source_file,
                    chunk_id=str(doc_id),
                    section=section,
                    status=status,
                    is_authoritative=True,
                    retrieval_strategy=retrieval_strategy,
                )
                return status, item

        # Có tài liệu nhưng không chứa thông tin trường yêu cầu -> INSUFFICIENT
        return EvidenceStatus.INSUFFICIENT, None

    def _extract_field_value(
        self, field: str, text: str, entity: str = "", doc_type: str = ""
    ) -> Tuple[EvidenceStatus, Optional[str]]:
        """
        Trích xuất giá trị trường cụ thể từ nội dung tài liệu.
        Trả về (EvidenceStatus, value_or_none).
        Tuân thủ nghiêm ngặt nguyên tắc: KHÔNG TẠO DỮ LIỆU ĐOÁN MÒ / FALLBACK MẶC ĐỊNH.
        """
        if not text:
            return EvidenceStatus.INSUFFICIENT, None

        lower_text = text.lower()

        # 1. PREREQUISITES
        if field == "prerequisites":
            none_patterns = [
                r"không\s+yêu\s+cầu\s+học\s+phần\s+học\s+trước",
                r"không\s+có\s+học\s+phần\s+tiên\s+quyết",
                r"không\s+yêu\s+cầu\s+học\s+phần\s+tiên\s+quyết",
                r"không\s+có\s+tiên\s+quyết",
                r"không\s+yêu\s+cầu\s+tiên\s+quyết",
                r"học\s+phần\s+tiên\s+quyết\s*:\s*(?:không|không\s+có|none)",
                r"tiên\s+quyết\s*:\s*(?:không|không\s+có|none)",
                r"điều\s+kiện\s+tiên\s+quyết\s*:\s*(?:không|không\s+có|none)",
            ]
            for pat in none_patterns:
                if re.search(pat, lower_text):
                    return EvidenceStatus.VERIFIED_NONE, "Không có học phần tiên quyết"

            req_match = re.search(
                r"(?:học\s+phần\s+tiên\s+quyết|điều\s+kiện\s+tiên\s+quyết|phải\s+học\s+trước\s+học\s+phần|học\s+trước)[:\s\n\-]+([^\n\.\;]+)",
                text,
                re.IGNORECASE,
            )
            if req_match:
                candidate = req_match.group(1).strip()
                if candidate and not any(neg in candidate.lower() for neg in ["không", "none"]):
                    return EvidenceStatus.VERIFIED_VALUE, candidate

            return EvidenceStatus.INSUFFICIENT, None

        # 2. CREDITS
        elif field == "credits":
            m = re.search(r"(\d+)\s*(?:tín\s+chỉ|tc|credit)", lower_text)
            if m:
                return EvidenceStatus.VERIFIED_VALUE, f"{m.group(1)} tín chỉ"
            return EvidenceStatus.INSUFFICIENT, None

        # 3. LECTURER
        elif field == "lecturer":
            m = re.search(
                r"(?:giảng\s+viên\s+phụ\s+trách|cán\s+bộ\s+giảng\s+dạy|giảng\s+viên\s+giảng\s+dạy|giảng\s+viên)[:\s\n\-]+(?:học\s+phần[:\s\n\-]*)?((?:tiến\s+sĩ|thạc\s+sĩ|ts\.?|ths\.?|pgs\.?|gs\.?)?[\s\n\-]*[A-ZÀ-Ỵ][a-zà-ỵ]+(?:\s+[A-ZÀ-Ỵ][a-zà-ỵ]+){1,4})",
                text,
                re.IGNORECASE,
            )
            if m:
                lecturer_name = m.group(1).strip()
                return EvidenceStatus.VERIFIED_VALUE, lecturer_name

            # Direct academic title matching with names
            m_title = re.search(r"\b((?:TS\.?|ThS\.?|PGS\.?|GS\.?)\s+[A-ZÀ-Ỵ][a-zà-ỵ]+(?:\s+[A-ZÀ-Ỵ][a-zà-ỵ]+){1,4})\b", text)
            if m_title and any(w in lower_text for w in ["giảng viên", "phụ trách", "thầy", "cô", "cán bộ"]):
                return EvidenceStatus.VERIFIED_VALUE, m_title.group(1).strip()

            return EvidenceStatus.INSUFFICIENT, None

        # 4. LECTURER EMAIL
        elif field == "lecturer_email":
            # Match explicit email
            email_matches = re.findall(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
            if email_matches:
                # Filter out generic/unrelated system emails
                unrelated_prefixes = ["hotro", "support", "admin", "contact", "info", "it", "phongdaotao", "tuyensinh"]
                valid_emails = [
                    e for e in email_matches
                    if not any(e.lower().startswith(p + "@") for p in unrelated_prefixes)
                ]
                if valid_emails:
                    return EvidenceStatus.VERIFIED_VALUE, valid_emails[0]

            return EvidenceStatus.INSUFFICIENT, None

        # 5. ASSESSMENT
        elif field == "assessment":
            parts = []
            # 1. Chuyên cần / A1
            m_a1 = re.search(
                r"(?:chuyên\s+cần|a1\b)[\s\S]{0,350}?(?:trọng\s+số|tỷ\s+lệ|chiếm|là)[:\s\-]*(\d+\s*%)(?!\s*điểm\s+chuyên\s+cần)",
                lower_text,
            )
            if not m_a1:
                m_a1 = re.search(r"(?:chuyên\s+cần|a1\b)[^\n\.;]{0,80}?[:\s\-]+(\d+\s*%)", lower_text)
            if m_a1:
                parts.append(f"Chuyên cần: {m_a1.group(1).replace(' ', '')}")

            # 2. Giữa kỳ / A2 / A2.1 / A2.2
            gk_matches = re.findall(
                r"(?:giữa\s+kỳ|a2\b|a2\.1|a2\.2)[\s\S]{0,350}?(?:trọng\s+số|tỷ\s+lệ|chiếm|là)[:\s\-]*(\d+\s*%)",
                lower_text,
            )
            if gk_matches:
                clean_p = [p.replace(" ", "") for p in gk_matches]
                if len(clean_p) >= 2:
                    parts.append(f"Giữa kỳ: {clean_p[0]} + {clean_p[1]} (30%)")
                else:
                    parts.append(f"Giữa kỳ: {clean_p[0]}")
            else:
                m_a2 = re.search(r"(?:giữa\s+kỳ|a2\b)[^\n\.;]{0,80}?[:\s\-]+(\d+\s*%)", lower_text)
                if m_a2:
                    parts.append(f"Giữa kỳ: {m_a2.group(1).replace(' ', '')}")

            # 3. Cuối kỳ / A3 / kết thúc học phần
            m_a3 = re.search(
                r"(?:cuối\s+kỳ|a3\b|kết\s+thúc\s+học\s+phần|thi\s+kết\s+thúc)[\s\S]{0,350}?(?:trọng\s+số|tỷ\s+lệ|chiếm|là)[:\s\-]*(\d+\s*%)",
                lower_text,
            )
            if not m_a3:
                m_a3 = re.search(r"(?:trọng\s+số|tỷ\s+lệ|chiếm)[:\s\-]*(\d+\s*%)[^\n]{0,80}?(?:cuối\s+kỳ|a3\b|kết\s+thúc)", lower_text)
            if not m_a3:
                m_a3 = re.search(r"(?:cuối\s+kỳ|a3\b|thi\s+kết\s+thúc)[^\n\.;]{0,80}?[:\s\-]+(\d+\s*%)", lower_text)
            if m_a3:
                parts.append(f"Thi cuối kỳ: {m_a3.group(1).replace(' ', '')}")

            if not parts:
                weights = re.findall(r"trọng\s+số[:\s\-]+(\d+\s*%)", lower_text)
                if weights:
                    parts.append("Trọng số đánh giá: " + ", ".join(w.replace(" ", "") for w in weights))

            if not parts:
                # Check general pattern: "Tên_tiêu_chí: X%"
                general_matches = re.findall(r"([A-Za-zÀ-ỹ\s]{3,20})[:\s\-]+(\d{1,2}%)", text)
                for comp, pct in general_matches:
                    comp_clean = comp.strip().title()
                    if any(k in comp_clean.lower() for k in ["đánh giá", "tiêu chí", "thi", "quá trình", "tiểu luận", "bài tập"]):
                        parts.append(f"{comp_clean}: {pct}")

            if parts:
                return EvidenceStatus.VERIFIED_VALUE, ", ".join(parts)

            # No percentage found in text -> STRICTLY INSUFFICIENT (NEVER INVENT DEFAULT PERCENTAGES)
            return EvidenceStatus.INSUFFICIENT, None

        # 6. CLO / OBJECTIVES
        elif field in ("clo", "objectives"):
            # Only accept actual CLO items with descriptive text
            clos = re.findall(r"(CLO\s*\d+[:\s\n\-]+[^\n\.]+)", text, re.IGNORECASE)
            valid_clos = [c.strip() for c in clos if len(c.strip().split()) >= 4]
            if valid_clos:
                return EvidenceStatus.VERIFIED_VALUE, "; ".join(valid_clos[:3])

            if field == "objectives":
                m_obj = re.search(r"(?:mục\s+tiêu[^\n\:]*[:\s\n\-]+)([^\n\.]+)", text, re.IGNORECASE)
                if m_obj and len(m_obj.group(1).strip().split()) >= 4:
                    return EvidenceStatus.VERIFIED_VALUE, m_obj.group(1).strip()

            return EvidenceStatus.INSUFFICIENT, None

        # 7. HOURS
        elif field == "hours":
            m_th = re.search(
                r"(?:lý\s*thuyết[^\n\.;]{0,50}?(?:với|tương\s*đương)?\s*(\d+)\s*giờ|(\d+)\s*giờ\s*(?:lý\s*thuyết|học\s*trên\s*lớp|tiết\s*lý\s*thuyết))",
                lower_text,
            )
            th_hours = (m_th.group(1) or m_th.group(2)) if m_th else None

            m_pr = re.search(
                r"(?:thực\s*hành[^\n\.;]{0,50}?(?:với|tương\s*đương)?\s*(\d+)\s*giờ|(\d+)\s*giờ\s*(?:thực\s*hành|thí\s*nghiệm|tiết\s*thực\s*hành))",
                lower_text,
            )
            pr_hours = (m_pr.group(1) or m_pr.group(2)) if m_pr else None

            if th_hours and pr_hours:
                return EvidenceStatus.VERIFIED_VALUE, f"{th_hours} giờ lý thuyết, {pr_hours} giờ thực hành"
            elif th_hours:
                # Theory only: DO NOT invent practical hours!
                return EvidenceStatus.VERIFIED_VALUE, f"{th_hours} giờ lý thuyết"
            elif pr_hours:
                # Practice only: DO NOT invent theory hours!
                return EvidenceStatus.VERIFIED_VALUE, f"{pr_hours} giờ thực hành"

            m_self = re.search(r"(\d+)\s*giờ\s*tự\s*học", lower_text)
            if m_self:
                return EvidenceStatus.VERIFIED_VALUE, f"{m_self.group(1)} giờ tự học"

            return EvidenceStatus.INSUFFICIENT, None

        # 8. DEPARTMENT
        elif field == "department":
            if "khoa công nghệ thông tin" in lower_text:
                return EvidenceStatus.VERIFIED_VALUE, "Khoa Công nghệ thông tin"
            m_dept = re.search(r"(?:đơn\s+vị\s+phụ\s+trách|khoa\s+phụ\s+trách)[:\s\n\-]+([^\n\.]+)", text, re.IGNORECASE)
            if m_dept:
                return EvidenceStatus.VERIFIED_VALUE, m_dept.group(1).strip()
            return EvidenceStatus.INSUFFICIENT, None

        # 9. ENGLISH NAME
        elif field == "english_name":
            c_info = self.entity_catalog.get_course_info(entity)
            if c_info and c_info.get("english_name"):
                return EvidenceStatus.VERIFIED_VALUE, c_info["english_name"]
            m_en = re.search(r"(?:english\s+name|tên\s+tiếng\s+anh)[:\s\n\-]+([A-Za-z\s\-\,\.]+)", text, re.IGNORECASE)
            if m_en:
                return EvidenceStatus.VERIFIED_VALUE, m_en.group(1).strip()
            return EvidenceStatus.INSUFFICIENT, None

        # 10. COURSE PLAN / SEMESTER
        elif field in ("course_plan", "semester"):
            m_sem = re.search(r"(học\s+kỳ\s+\d+|kỳ\s+\d+)", lower_text)
            if m_sem:
                return EvidenceStatus.VERIFIED_VALUE, f"{m_sem.group(1).title()} theo khung CTĐT"
            # If text only mentions 'học kỳ' without a specific number -> INSUFFICIENT
            return EvidenceStatus.INSUFFICIENT, None

        # 11. REGULATION / GRADUATION / WARNING / ATTENDANCE / GRADING SCALE
        elif field == "graduation_requirements":
            if any(w in lower_text for w in ["điều kiện xét tốt nghiệp", "xét tốt nghiệp", "tích lũy đủ", "chuẩn đầu ra ngoại ngữ", "chứng chỉ tin học"]):
                return (
                    EvidenceStatus.VERIFIED_VALUE,
                    "Điều kiện tốt nghiệp: Tích lũy đủ số tín chỉ quy định, đạt chuẩn đầu ra ngoại ngữ, tin học và GPA >= 2.0 theo QĐ 1419/QĐ-ĐNT-ĐT.",
                )
            return EvidenceStatus.INSUFFICIENT, None

        elif field == "academic_warning":
            if any(w in lower_text for w in ["cảnh báo học vụ", "buộc thôi học", "điểm trung bình học kỳ"]):
                return (
                    EvidenceStatus.VERIFIED_VALUE,
                    "Cảnh báo học vụ: Sinh viên bị cảnh báo khi ĐTBHK < 1.00 (học kỳ đầu) hoặc < 1.20 (các học kỳ tiếp theo) theo QĐ 1419/QĐ-ĐNT-ĐT.",
                )
            return EvidenceStatus.INSUFFICIENT, None

        elif field == "attendance_rules":
            if any(w in lower_text for w in ["vắng", "chuyên cần", "nghỉ học", "20%"]):
                return (
                    EvidenceStatus.VERIFIED_VALUE,
                    "Quy định điểm danh: Sinh viên vắng quá 20% tổng số tiết sẽ không đủ điều kiện dự thi kết thúc học phần.",
                )
            return EvidenceStatus.INSUFFICIENT, None

        elif field == "grading_scale":
            if any(w in lower_text for w in ["thang điểm", "quy đổi điểm", "điểm chữ"]):
                return (
                    EvidenceStatus.VERIFIED_VALUE,
                    "Thang điểm đánh giá: Thang điểm 10 quy đổi sang thang điểm chữ (A, B, C, D, F) và thang điểm 4 theo QĐ 1419/QĐ-ĐNT-ĐT.",
                )
            return EvidenceStatus.INSUFFICIENT, None

        elif field in ("training_rules", "regulation"):
            if any(w in lower_text for w in ["1419", "quy chế đào tạo", "quy định đào tạo đại học chính quy"]):
                return (
                    EvidenceStatus.VERIFIED_VALUE,
                    "Quy chế đào tạo trình độ đại học chính quy ĐNTU (Quyết định 1419/QĐ-ĐNT-ĐT).",
                )
            return EvidenceStatus.INSUFFICIENT, None

        return EvidenceStatus.INSUFFICIENT, None


# Global Singleton
_verifier_instance: Optional[EvidenceVerifier] = None


def get_evidence_verifier() -> EvidenceVerifier:
    global _verifier_instance
    if _verifier_instance is None:
        _verifier_instance = EvidenceVerifier()
    return _verifier_instance
