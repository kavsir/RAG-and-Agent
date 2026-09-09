"""
Curriculum Parser: Bộ phân tích cú pháp chương trình đào tạo từ các tài liệu docx có thẩm quyền.
Trích xuất dữ liệu dạng bảng/quan hệ vào Structured Academic Store (SQLite) kèm provenance đầy đủ.
"""
import re
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from src.config.settings import settings
from src.ingestion.loaders import load_docx
from src.agent_core.academic_store import StructuredAcademicStore, get_academic_store

logger = logging.getLogger(__name__)


class CurriculumParser:
    """
    Parser chuyển đổi tài liệu Word CTĐT thành các bản ghi quan hệ có cấu trúc và bằng chứng xuất xứ.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or (settings.DATA_RAW_DIR / "curriculum")

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Tính mã băm SHA-256 của tệp nguồn để đảm bảo toàn vẹn bằng chứng (Evidence Grounding)."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                sha256.update(block)
        return sha256.hexdigest()

    def parse_file(self, file_path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Phân tích một tệp docx CTĐT.
        Trả về tuple (curriculum_info, list_of_courses).
        """
        source_hash = self.compute_file_hash(file_path)
        now_ts = datetime.now(timezone.utc).isoformat()
        text = load_docx(str(file_path))
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # 1. Nhận diện Ngành và Khóa
        cohort = "K19"
        title_text = " ".join(lines[:3]).lower()
        fname_lower = file_path.name.lower()

        if "hệ thống thông tin" in title_text or "httt" in fname_lower:
            major = "Hệ thống thông tin"
            major_slug = "HTTT"
        elif "khoa học máy tính" in title_text or "khmt" in fname_lower:
            major = "Khoa học máy tính"
            major_slug = "KHMT"
        elif "công nghệ thông tin" in title_text or "cntt" in fname_lower:
            major = "Công nghệ thông tin"
            major_slug = "CNTT"
        else:
            major = "Khoa học máy tính"
            major_slug = "KHMT"

        curriculum_id = f"{cohort}_{major_slug}"

        current_semester = 0
        current_section = "Thông tin chung"
        current_track = None
        current_type = "COMPULSORY"

        courses: List[Dict[str, Any]] = []

        for line in lines:
            # Nhận diện tiêu đề học kỳ: "HỌC KỲ 1 (12 tín chỉ)", "Học kỳ 1 – 12 tín chỉ"
            sem_match = re.search(r"Học\s+kỳ\s+(\d+)", line, re.IGNORECASE)
            if sem_match:
                current_semester = int(sem_match.group(1))
                current_section = line
                current_type = "COMPULSORY"
                continue

            # Thực tập và tốt nghiệp (Học kỳ 10 / 11)
            if re.search(r"THỰC\s+TẬP\s+VÀ\s+TỐT\s+NGHIỆP", line, re.IGNORECASE):
                current_semester = 10
                current_section = "Thực tập và tốt nghiệp"
                current_type = "GRADUATION"
                continue

            # Các học phần theo kế hoạch nhà trường (Đại cương chung toàn trường)
            if re.search(r"CÁC\s+HỌC\s+PHẦN\s+THEO\s+KẾ\s+HOẠCH", line, re.IGNORECASE) or re.search(r"Các\s+học\s+phần\s+theo\s+kế\s+hoạch", line, re.IGNORECASE):
                current_semester = 0
                current_section = "Học phần theo kế hoạch nhà trường"
                current_type = "GENERAL"
                continue

            # Danh sách học phần lựa chọn
            if re.search(r"DANH\s+SÁCH\s+HỌC\s+PHẦN\s+LỰA\s+CHỌN", line, re.IGNORECASE) or re.search(r"Danh\s+sách\s+học\s+phần\s+lựa\s+chọn", line, re.IGNORECASE):
                current_semester = 0
                current_section = "Danh sách học phần lựa chọn"
                current_type = "ELECTIVE"
                continue

            # Nhận diện chuyên ngành / định hướng
            if re.search(r"CHUYÊN\s+NGÀNH\s+KHOA\s+HỌC\s+DỮ\s+LIỆU", line, re.IGNORECASE):
                current_track = "Khoa học dữ liệu"
                current_type = "SPECIALIZATION"
                continue
            if re.search(r"CHUYÊN\s+NGÀNH\s+HỆ\s+THỐNG\s+NHÚNG", line, re.IGNORECASE):
                current_track = "Hệ thống nhúng và IoT"
                current_type = "SPECIALIZATION"
                continue
            if re.search(r"CHUYÊN\s+NGÀNH\s+KỸ\s+THUẬT\s+PHẦN\s+MỀM", line, re.IGNORECASE):
                current_track = "Kỹ thuật phần mềm"
                current_type = "SPECIALIZATION"
                continue

            # Bỏ qua các tiêu đề thể chất, quốc phòng không có mã môn chuẩn
            if re.search(r"Giáo\s+dục\s+thể\s+chất", line, re.IGNORECASE) or re.search(r"Giáo\s+dục\s+quốc\s+phòng", line, re.IGNORECASE):
                continue

            # Cú pháp dòng môn học: FIT4001 - Nhập môn công nghệ thông tin - 3 tín chỉ
            # hoặc: FIT5001 - Thực tập tốt nghiệp - 4 tín chỉ - Học kỳ 10
            # hỗ trợ cả dấu gạch ngang chuẩn (-) và en-dash (–)
            course_match = re.match(
                r"^([A-Z]{2,4}\d{4})\s*[-–]\s*(.+?)\s*[-–]\s*(\d+)\s*tín\s*chỉ(?:\s*[-–]\s*(.*))?$",
                line,
                re.IGNORECASE,
            )
            if course_match:
                code = course_match.group(1).upper()
                name = course_match.group(2).strip()
                credits = int(course_match.group(3))
                extra = course_match.group(4)
                sem = current_semester

                # Nếu có học kỳ ghi rõ ở phần đuôi
                if extra:
                    sem_extra = re.search(r"Học\s+kỳ\s+(\d+)", extra, re.IGNORECASE)
                    if sem_extra:
                        sem = int(sem_extra.group(1))

                # Xác định chunk_id định danh duy nhất cho provenance
                chunk_id = f"{curriculum_id}_{code}_SEM{sem}"

                courses.append({
                    "curriculum_id": curriculum_id,
                    "course_code": code,
                    "course_name": name,
                    "semester": sem,
                    "credits": credits,
                    "course_type": current_type,
                    "specialization_track": current_track,
                    "prerequisites": None,
                    "source_file": file_path.name,
                    "source_section": current_section,
                    "source_chunk_id": chunk_id,
                    "source_hash": source_hash,
                    "ingestion_timestamp": now_ts,
                })

        # Tính tổng số tín chỉ bắt buộc + đại cương + tốt nghiệp
        total_credits = sum(c["credits"] for c in courses if c["course_type"] != "ELECTIVE")

        curriculum_info = {
            "curriculum_id": curriculum_id,
            "cohort": cohort,
            "major": major,
            "total_credits": total_credits,
            "source_file": file_path.name,
            "source_hash": source_hash,
            "ingestion_timestamp": now_ts,
        }

        return curriculum_info, courses

    def ingest_all_curricula(self, store: Optional[StructuredAcademicStore] = None) -> Dict[str, Any]:
        """
        Đọc và nạp toàn bộ các tệp docx trong data_raw/curriculum vào SQLite Store.
        """
        store = store or get_academic_store()
        docx_files = list(self.data_dir.glob("*.docx"))
        if not docx_files:
            logger.warning(f"No docx curriculum files found in {self.data_dir}")
            return {"curricula_loaded": 0, "courses_loaded": 0}

        curricula_count = 0
        courses_count = 0

        for f in docx_files:
            try:
                curr_info, courses = self.parse_file(f)
                store.insert_curriculum(curr_info)
                store.clear_curriculum_courses(curr_info["curriculum_id"])
                store.insert_courses(courses)
                curricula_count += 1
                courses_count += len(courses)
                logger.info(f"Ingested curriculum {curr_info['curriculum_id']} ({curr_info['major']}): {len(courses)} courses")
            except Exception as e:
                logger.error(f"Error ingesting {f.name}: {e}", exc_info=True)

        return {
            "curricula_loaded": curricula_count,
            "courses_loaded": courses_count,
        }


def ensure_curriculum_data_loaded(store: Optional[StructuredAcademicStore] = None) -> None:
    """Hàm tiện ích nạp dữ liệu CTĐT nếu chưa có."""
    parser = CurriculumParser()
    parser.ingest_all_curricula(store=store)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = CurriculumParser().ingest_all_curricula()
    print("Ingestion result:", res)
    store = get_academic_store()
    print("Database counts:", store.count_records())
