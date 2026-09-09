"""
Structured Academic Store: Kho lưu trữ tri thức học vụ có cấu trúc (Round A1).
Hiện thực hóa việc truy xuất dữ liệu chương trình đào tạo quan hệ/bảng biểu (SQLite)
với xuất xứ đầy đủ (source provenance), cam kết p95 < 100ms, không rò rỉ chéo chương trình,
và không phụ thuộc vào LLM.
"""
import sqlite3
import hashlib
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from src.config.settings import settings
from src.agent_core.schemas import (
    EntityType,
    AcademicOperation,
    AcademicQueryPlan,
    EvidenceItem,
    EvidenceStatus,
)

logger = logging.getLogger(__name__)

# Ánh xạ tên ngành thông dụng sang tên ngành chuẩn hóa
MAJOR_CANONICAL_MAP = {
    "khmt": "Khoa học máy tính",
    "khoa học máy tính": "Khoa học máy tính",
    "computer science": "Khoa học máy tính",
    "cntt": "Công nghệ thông tin",
    "công nghệ thông tin": "Công nghệ thông tin",
    "information technology": "Công nghệ thông tin",
    "it": "Công nghệ thông tin",
    "httt": "Hệ thống thông tin",
    "hệ thống thông tin": "Hệ thống thông tin",
    "information systems": "Hệ thống thông tin",
}


def normalize_cohort(cohort: str) -> str:
    """Chuẩn hóa mã khóa học (ví dụ: 'k19', ' khóa 19' -> 'K19')."""
    if not cohort:
        return "K19"
    c = cohort.strip().upper()
    if c.startswith("KHÓA") or c.startswith("KHOA"):
        c = c.replace("KHÓA", "").replace("KHOA", "").strip()
        return f"K{c}"
    if not c.startswith("K") and c.isdigit():
        return f"K{c}"
    return c


def normalize_major(major: str) -> str:
    """Chuẩn hóa tên ngành học."""
    if not major:
        return "Khoa học máy tính"
    m = major.strip().lower()
    return MAJOR_CANONICAL_MAP.get(m, major.strip())


class StructuredAcademicStore:
    """
    Kho lưu trữ dữ liệu học vụ có cấu trúc dựa trên SQLite (`runtime/academic_store.sqlite3`).
    Đảm bảo:
    - 0 LLM calls cho deterministic lookups
    - P95 latency < 100ms
    - Xuất xứ đầy đủ trên từng bản ghi (source_file, source_section, source_chunk_id, source_hash, ingestion_timestamp)
    - Cô lập chặt chẽ theo (cohort, major) chống rò rỉ chéo CTĐT (CROSS_CURRICULUM_LEAKAGE = 0).
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (settings.RUNTIME_DIR / "academic_store.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Lấy hoặc tạo kết nối thread-local an toàn đa luồng."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=5.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        """Đóng kết nối thread-local nếu có."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None

    def _init_db(self) -> None:
        """Khởi tạo cấu trúc bảng và index cho kho dữ liệu học vụ."""
        conn = self._get_connection()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS curriculums (
                    curriculum_id TEXT PRIMARY KEY,
                    cohort TEXT NOT NULL,
                    major TEXT NOT NULL,
                    total_credits INTEGER NOT NULL DEFAULT 0,
                    source_file TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    ingestion_timestamp TEXT NOT NULL,
                    UNIQUE(cohort, major)
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS curriculum_courses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    curriculum_id TEXT NOT NULL,
                    course_code TEXT NOT NULL,
                    course_name TEXT NOT NULL,
                    semester INTEGER NOT NULL,
                    credits INTEGER NOT NULL DEFAULT 0,
                    course_type TEXT NOT NULL DEFAULT 'COMPULSORY',
                    specialization_track TEXT,
                    prerequisites TEXT,
                    source_file TEXT NOT NULL,
                    source_section TEXT NOT NULL,
                    source_chunk_id TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    ingestion_timestamp TEXT NOT NULL,
                    FOREIGN KEY (curriculum_id) REFERENCES curriculums (curriculum_id) ON DELETE CASCADE
                );
            """)
            # Các index phục vụ tra cứu tức thì < 5ms
            conn.execute("CREATE INDEX IF NOT EXISTS idx_curriculums_cohort_major ON curriculums(cohort, major);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_courses_curriculum ON curriculum_courses(curriculum_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_courses_semester ON curriculum_courses(curriculum_id, semester);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_courses_code ON curriculum_courses(course_code);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_courses_name ON curriculum_courses(course_name);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_courses_type ON curriculum_courses(course_type);")

    def count_records(self) -> Dict[str, int]:
        """Đếm số lượng bản ghi hiện có trong kho dữ liệu."""
        conn = self._get_connection()
        c1 = conn.execute("SELECT COUNT(*) FROM curriculums;").fetchone()[0]
        c2 = conn.execute("SELECT COUNT(*) FROM curriculum_courses;").fetchone()[0]
        return {"curriculums": c1, "courses": c2}

    def insert_curriculum(self, curriculum_data: Dict[str, Any]) -> str:
        """Thêm hoặc cập nhật một chương trình đào tạo."""
        conn = self._get_connection()
        curriculum_id = curriculum_data.get("curriculum_id") or f"{curriculum_data['cohort']}_{curriculum_data['major']}"
        now_ts = datetime.now(timezone.utc).isoformat()
        with conn:
            conn.execute("""
                INSERT INTO curriculums (
                    curriculum_id, cohort, major, total_credits, source_file, source_hash, ingestion_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cohort, major) DO UPDATE SET
                    curriculum_id = excluded.curriculum_id,
                    total_credits = excluded.total_credits,
                    source_file = excluded.source_file,
                    source_hash = excluded.source_hash,
                    ingestion_timestamp = excluded.ingestion_timestamp;
            """, (
                curriculum_id,
                curriculum_data["cohort"],
                curriculum_data["major"],
                curriculum_data.get("total_credits", 0),
                curriculum_data.get("source_file", ""),
                curriculum_data.get("source_hash", ""),
                curriculum_data.get("ingestion_timestamp", now_ts),
            ))
        return curriculum_id

    def insert_courses(self, courses_data: List[Dict[str, Any]]) -> int:
        """Thêm danh sách môn học kèm thông tin xuất xứ."""
        if not courses_data:
            return 0
        conn = self._get_connection()
        now_ts = datetime.now(timezone.utc).isoformat()
        inserted = 0
        with conn:
            for c in courses_data:
                conn.execute("""
                    INSERT INTO curriculum_courses (
                        curriculum_id, course_code, course_name, semester, credits,
                        course_type, specialization_track, prerequisites,
                        source_file, source_section, source_chunk_id, source_hash, ingestion_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    c["curriculum_id"],
                    c["course_code"].upper(),
                    c["course_name"],
                    int(c["semester"]),
                    int(c.get("credits", 0)),
                    c.get("course_type", "COMPULSORY"),
                    c.get("specialization_track"),
                    c.get("prerequisites"),
                    c.get("source_file", ""),
                    c.get("source_section", ""),
                    c.get("source_chunk_id", ""),
                    c.get("source_hash", ""),
                    c.get("ingestion_timestamp", now_ts),
                ))
                inserted += 1
        return inserted

    def clear_curriculum_courses(self, curriculum_id: str) -> None:
        """Xóa toàn bộ môn học thuộc curriculum_id để nạp mới."""
        conn = self._get_connection()
        with conn:
            conn.execute("DELETE FROM curriculum_courses WHERE curriculum_id = ?;", (curriculum_id,))

    def get_curriculum(self, cohort: str, major: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin chương trình đào tạo theo Khóa và Ngành."""
        self._ensure_loaded()
        norm_cohort = normalize_cohort(cohort)
        norm_major = normalize_major(major)
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM curriculums WHERE UPPER(cohort) = UPPER(?) AND (LOWER(major) = LOWER(?) OR LOWER(major) LIKE LOWER(?));",
            (norm_cohort, norm_major, f"%{norm_major}%")
        ).fetchone()
        if row:
            return dict(row)
        return None

    def list_curriculum_courses(
        self,
        cohort: str,
        major: str,
        semester: Optional[int] = None,
        course_type: Optional[str] = None,
        track: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Lấy danh sách môn học của một CTĐT cụ thể.
        Đảm bảo CROSS_CURRICULUM_LEAKAGE = 0: chỉ lấy môn thuộc đúng curriculum_id đã resolve.
        """
        curr = self.get_curriculum(cohort, major)
        if not curr:
            return []

        curriculum_id = curr["curriculum_id"]
        conn = self._get_connection()

        query = "SELECT * FROM curriculum_courses WHERE curriculum_id = ?"
        params: List[Any] = [curriculum_id]

        if semester is not None:
            query += " AND semester = ?"
            params.append(semester)

        if course_type:
            query += " AND UPPER(course_type) = UPPER(?)"
            params.append(course_type)

        if track:
            query += " AND (specialization_track IS NULL OR LOWER(specialization_track) LIKE LOWER(?))"
            params.append(f"%{track}%")

        query += " ORDER BY semester ASC, course_code ASC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def find_course_placement(self, cohort: str, major: str, course_code: str) -> Optional[Dict[str, Any]]:
        """
        Xác định vị trí học kỳ của một môn học trong CTĐT của sinh viên.
        """
        curr = self.get_curriculum(cohort, major)
        if not curr:
            return None

        curriculum_id = curr["curriculum_id"]
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM curriculum_courses WHERE curriculum_id = ? AND UPPER(course_code) = UPPER(?);",
            (curriculum_id, course_code.strip())
        ).fetchone()
        if row:
            res = dict(row)
            res["curriculum_total_credits"] = curr["total_credits"]
            return res
        return None

    def get_total_credits(self, cohort: str, major: str) -> Optional[Dict[str, Any]]:
        """Lấy tổng số tín chỉ và cơ cấu tín chỉ theo học kỳ."""
        curr = self.get_curriculum(cohort, major)
        if not curr:
            return None

        curriculum_id = curr["curriculum_id"]
        conn = self._get_connection()

        # Tính tổng theo từng kỳ
        sem_rows = conn.execute("""
            SELECT semester, SUM(credits) as semester_credits, COUNT(*) as course_count
            FROM curriculum_courses
            WHERE curriculum_id = ?
            GROUP BY semester
            ORDER BY semester ASC;
        """, (curriculum_id,)).fetchall()

        semesters = [dict(r) for r in sem_rows]
        sum_credits = sum(s["semester_credits"] for s in semesters)

        return {
            "curriculum_id": curriculum_id,
            "cohort": curr["cohort"],
            "major": curr["major"],
            "total_credits": curr["total_credits"] or sum_credits,
            "calculated_credits": sum_credits,
            "semesters": semesters,
            "source_file": curr["source_file"],
            "source_hash": curr["source_hash"],
            "ingestion_timestamp": curr["ingestion_timestamp"],
        }

    def execute_query(self, plan: AcademicQueryPlan) -> Dict[str, Any]:
        """
        Thực thi một AcademicQueryPlan có kiểu và trả về kết quả cấu trúc kèm bằng chứng xuất xứ.
        """
        filters = plan.filters or {}
        cohort = filters.get("cohort", "K19")
        major = filters.get("major", "Khoa học máy tính")
        op = plan.operation

        if op == AcademicOperation.GET_TOTAL_CREDITS.value or op == "GET_TOTAL_CREDITS":
            data = self.get_total_credits(cohort, major)
            if data:
                return {
                    "status": "success",
                    "operation": op,
                    "data": data,
                    "record_count": 1,
                    "source_provenance": {
                        "source_file": data.get("source_file"),
                        "source_hash": data.get("source_hash"),
                        "ingestion_timestamp": data.get("ingestion_timestamp"),
                    }
                }
            return {"status": "empty", "operation": op, "data": None, "record_count": 0}

        elif op == AcademicOperation.GET_SEMESTER_COURSES.value or op == "GET_SEMESTER_COURSES":
            semester = filters.get("semester")
            courses = self.list_curriculum_courses(cohort, major, semester=semester)
            prov = courses[0] if courses else {}
            return {
                "status": "success" if courses else "empty",
                "operation": op,
                "data": courses,
                "record_count": len(courses),
                "source_provenance": {
                    "source_file": prov.get("source_file"),
                    "source_section": prov.get("source_section"),
                    "source_chunk_id": prov.get("source_chunk_id"),
                    "source_hash": prov.get("source_hash"),
                    "ingestion_timestamp": prov.get("ingestion_timestamp"),
                }
            }

        elif op == AcademicOperation.FIND_COURSE_SEMESTER.value or op == "FIND_COURSE_SEMESTER":
            course_code = filters.get("course_code", "")
            placement = self.find_course_placement(cohort, major, course_code)
            if placement:
                return {
                    "status": "success",
                    "operation": op,
                    "data": placement,
                    "record_count": 1,
                    "source_provenance": {
                        "source_file": placement.get("source_file"),
                        "source_section": placement.get("source_section"),
                        "source_chunk_id": placement.get("source_chunk_id"),
                        "source_hash": placement.get("source_hash"),
                        "ingestion_timestamp": placement.get("ingestion_timestamp"),
                    }
                }
            return {"status": "empty", "operation": op, "data": None, "record_count": 0}

        elif op == AcademicOperation.LIST_COURSES.value or op == "LIST_COURSES":
            semester = filters.get("semester")
            courses = self.list_curriculum_courses(cohort, major, semester=semester)
            prov = courses[0] if courses else {}
            return {
                "status": "success" if courses else "empty",
                "operation": op,
                "data": courses,
                "record_count": len(courses),
                "source_provenance": {
                    "source_file": prov.get("source_file"),
                    "source_section": prov.get("source_section"),
                    "source_chunk_id": prov.get("source_chunk_id"),
                    "source_hash": prov.get("source_hash"),
                    "ingestion_timestamp": prov.get("ingestion_timestamp"),
                }
            }

        else:
            # Truy vấn mặc định theo CTĐT
            courses = self.list_curriculum_courses(cohort, major)
            prov = courses[0] if courses else {}
            return {
                "status": "success" if courses else "empty",
                "operation": op,
                "data": courses,
                "record_count": len(courses),
                "source_provenance": {
                    "source_file": prov.get("source_file"),
                    "source_section": prov.get("source_section"),
                    "source_chunk_id": prov.get("source_chunk_id"),
                    "source_hash": prov.get("source_hash"),
                    "ingestion_timestamp": prov.get("ingestion_timestamp"),
                }
            }

    def _ensure_loaded(self) -> None:
        """Tự động nạp dữ liệu từ thư mục curriculum nếu kho dữ liệu đang trống."""
        try:
            conn = self._get_connection()
            c1 = conn.execute("SELECT COUNT(*) FROM curriculums;").fetchone()[0]
            if c1 == 0:
                from src.ingestion.curriculum_parser import CurriculumParser
                parser = CurriculumParser()
                parser.ingest_all_curricula(store=self)
        except Exception as e:
            logger.warning(f"Auto-ingestion note: {e}")


# Singleton instance
_store_instance: Optional[StructuredAcademicStore] = None
_store_lock = threading.Lock()


def get_academic_store() -> StructuredAcademicStore:
    """Lấy thể hiện singleton của StructuredAcademicStore."""
    global _store_instance
    if _store_instance is None:
        with _store_lock:
            if _store_instance is None:
                _store_instance = StructuredAcademicStore()
    return _store_instance
