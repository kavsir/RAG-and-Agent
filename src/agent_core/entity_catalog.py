"""
Entity Catalog for Goal-Driven Agent Core V1.
Authoritative registry of academic courses from real data (data_raw/):
- Detailed course catalog (outlines available: FIT4104, FIT4113, FIT4117, FIT4201)
- Curriculum course code catalog (all 63 CTĐT K19 course codes from docx)
- Exact unknown entity detection (no guessing or fallback)
- Entity conflict detection (e.g. code X with alias/name of course Y)
"""
import re
from typing import Dict, Any, List, Optional, Tuple, Set


class EntityCatalog:
    """
    Catalog thực thể học vụ chính thống.
    Đảm bảo 100% không bịa đặt mã môn hoặc đoán mò mã môn lạ.
    """

    # 1. Các học phần có đề cương chi tiết đầy đủ trong data_raw/course_detail/
    DETAILED_COURSES: Dict[str, Dict[str, Any]] = {
        "FIT4104": {
            "code": "FIT4104",
            "name": "Dự án thiết kế, lập trình Full-Stack",
            "english_name": "Full-Stack Design and Programming",
            "aliases": [
                "full-stack", "full stack", "fullstack",
                "dự án thiết kế lập trình full-stack", "lập trình full-stack",
                "dự án full-stack", "dự án full stack", "thiết kế lập trình full-stack",
                "công nghệ web"
            ],
            "credits": 3,
            "lecturer": "ThS. Phạm Văn Tiệp",
            "lecturer_email": "tieppv@dainam.edu.vn",
            "hours": "15 giờ lý thuyết, 30 giờ thực hành",
            "department": "Khoa Công nghệ thông tin",
            "has_outline": True,
        },
        "FIT4113": {
            "code": "FIT4113",
            "name": "Công nghệ điện toán đám mây",
            "english_name": "Cloud computing technologies",
            "aliases": [
                "điện toán đám mây", "cloud computing",
                "công nghệ điện toán đám mây", "đám mây"
            ],
            "credits": 2,
            "lecturer": "TS. Trần Quý Nam",
            "lecturer_email": "namtq.dn@dainam.edu.vn",
            "hours": "15 giờ lý thuyết, 15 giờ thực hành",
            "department": "Khoa Công nghệ thông tin",
            "has_outline": True,
        },
        "FIT4117": {
            "code": "FIT4117",
            "name": "Quản trị dự án CNTT",
            "english_name": "IT Project Management",
            "aliases": [
                "quản trị dự án cntt", "quản trị dự án",
                "quản trị dự án công nghệ thông tin", "it project management"
            ],
            "credits": 2,
            "lecturer": "ThS. Phan Thị Tố Nga",
            "lecturer_email": "ngaptt@dainam.edu.vn",
            "hours": "15 giờ lý thuyết, 15 giờ thực hành",
            "department": "Khoa Công nghệ thông tin",
            "has_outline": True,
        },
        "FIT4201": {
            "code": "FIT4201",
            "name": "Hệ thống nhúng",
            "english_name": "Embedded Systems",
            "aliases": [
                "hệ thống nhúng", "embedded systems", "embedded system",
                "nhúng"
            ],
            "credits": 2,
            "lecturer": "TS. Trần Đăng Công",
            "lecturer_email": "congtd@dainam.edu.vn",
            "hours": "15 giờ lý thuyết, 15 giờ thực hành",
            "department": "Khoa Công nghệ thông tin",
            "has_outline": True,
        },
    }

    # 2. Toàn bộ 63 môn học thực tế từ 3 file docx CTĐT K19 (data_raw/curriculum/)
    CURRICULUM_COURSES: Dict[str, Dict[str, Any]] = {
        "BBA3004": {"name": "Khởi nghiệp và đổi mới sáng tạo", "credits": 3},
        "CSC4001": {"name": "Kho dữ liệu", "credits": 3},
        "CSC4002": {"name": "Dữ liệu lớn", "credits": 3},
        "CSC4003": {"name": "Khai phá dữ liệu", "credits": 3},
        "CSC4004": {"name": "Học máy", "credits": 3},
        "CSC4005": {"name": "Học sâu", "credits": 3},
        "CSC4006": {"name": "Trực quan và phân tích dữ liệu", "credits": 3},
        "CSC4007": {"name": "Xử lý ngôn ngữ tự nhiên", "credits": 3},
        "DNU1003": {"name": "Chủ nghĩa xã hội khoa học", "credits": 2},
        "DNU1004": {"name": "Lịch sử Đảng Cộng sản Việt Nam", "credits": 2},
        "DNU1005": {"name": "Tư tưởng Hồ Chí Minh", "credits": 2},
        "DNU1006": {"name": "Kỹ năng mềm cơ bản", "credits": 3},
        "DNU1007": {"name": "Kỹ năng mềm nâng cao", "credits": 3},
        "DNU1008": {"name": "Giáo dục thể chất 1", "credits": 1},
        "DNU1009": {"name": "Giáo dục thể chất 2", "credits": 1},
        "DNU1010": {"name": "Giáo dục thể chất 3", "credits": 1},
        "DNU1011": {"name": "Giáo dục Quốc phòng và An ninh 1", "credits": 3},
        "DNU1012": {"name": "Giáo dục Quốc phòng và An ninh 2", "credits": 2},
        "DNU1013": {"name": "Giáo dục Quốc phòng và An ninh 3", "credits": 2},
        "DNU1014": {"name": "Giáo dục Quốc phòng và An ninh 4", "credits": 4},
        "ENG2001": {"name": "Tiếng Anh 1", "credits": 3},
        "ENG2002": {"name": "Tiếng Anh 2", "credits": 3},
        "ENG2003": {"name": "Tiếng Anh 3", "credits": 3},
        "ENG2004": {"name": "Tiếng Anh 4", "credits": 3},
        "FIT3001": {"name": "Giải tích", "credits": 3},
        "FIT3002": {"name": "Đại số tuyến tính và tối ưu", "credits": 3},
        "FIT3003": {"name": "Toán rời rạc", "credits": 3},
        "FIT3004": {"name": "Xác suất thống kê và phân tích dữ liệu", "credits": 3},
        "FIT4001": {"name": "Nhập môn công nghệ thông tin", "credits": 3},
        "FIT4002": {"name": "Kiến trúc và hệ điều hành máy tính", "credits": 3},
        "FIT4003": {"name": "Lập trình cơ bản", "credits": 3},
        "FIT4004": {"name": "Cấu trúc dữ liệu và giải thuật", "credits": 3},
        "FIT4005": {"name": "Cơ sở dữ liệu", "credits": 3},
        "FIT4006": {"name": "Mạng máy tính", "credits": 2},
        "FIT4007": {"name": "Lập trình hướng đối tượng", "credits": 3},
        "FIT4008": {"name": "Hệ quản trị cơ sở dữ liệu", "credits": 3},
        "FIT4009": {"name": "Phân tích, thiết kế hệ thống thông tin", "credits": 3},
        "FIT4010": {"name": "Công nghệ phần mềm", "credits": 3},
        "FIT4011": {"name": "Trí tuệ nhân tạo", "credits": 3},
        "FIT4012": {"name": "Nhập môn an toàn, bảo mật thông tin", "credits": 3},
        "FIT4013": {"name": "Hệ thống máy tính", "credits": 3},
        "FIT4014": {"name": "Thiết kế web và triển khai hệ thống phần mềm", "credits": 3},
        "FIT4017": {"name": "Hội nhập và Quản trị phần mềm doanh nghiệp", "credits": 3},
        "FIT4018": {"name": "Lập trình Python", "credits": 2},
        "FIT4101": {"name": "Kiến trúc và thiết kế phần mềm", "credits": 2},
        "FIT4102": {"name": "Lập trình mobile", "credits": 3},
        "FIT4103": {"name": "Nhập môn học máy", "credits": 2},
        "FIT4104": {"name": "Dự án thiết kế, lập trình Full-Stack", "credits": 3},
        "FIT4110": {"name": "Dịch vụ kết nối và Công nghệ nền tảng", "credits": 2},
        "FIT4111": {"name": "Phát triển phần mềm mã nguồn mở", "credits": 2},
        "FIT4112": {"name": "Dữ liệu lớn, khai phá dữ liệu", "credits": 2},
        "FIT4113": {"name": "Công nghệ điện toán đám mây", "credits": 2},
        "FIT4114": {"name": "Cơ sở dữ liệu phân tán", "credits": 2},
        "FIT4115": {"name": "Kiểm thử phần mềm", "credits": 2},
        "FIT4116": {"name": "Thị giác máy tính", "credits": 2},
        "FIT4117": {"name": "Quản trị dự án công nghệ thông tin", "credits": 2},
        "FIT4118": {"name": "Công nghệ thông tin trong chuyển đổi số", "credits": 2},
        "FIT4201": {"name": "Hệ thống nhúng", "credits": 2},
        "FIT4202": {"name": "Tổng quan về IoT và Lập trình nhúng", "credits": 2},
        "FIT4203": {"name": "Lập trình IoT", "credits": 3},
        "FIT4204": {"name": "Triển khai, phát triển ứng dụng AI, IoT", "credits": 3},
        "FIT4210": {"name": "An toàn thông tin trong hệ thống IoT", "credits": 2},
        "FIT4302": {"name": "Giao diện và trải nghiệm người dùng", "credits": 2},
        "LAW2001": {"name": "Pháp luật đại cương", "credits": 2},
    }

    def __init__(self):
        # Map từ alias/tên sang mã môn
        self.alias_to_code: Dict[str, str] = {}
        for code, info in self.DETAILED_COURSES.items():
            self.alias_to_code[info["name"].lower()] = code
            for alias in info["aliases"]:
                self.alias_to_code[alias.lower()] = code

        # Bổ sung các môn trong CTĐT K19
        for code, info in self.CURRICULUM_COURSES.items():
            name_lower = info["name"].lower()
            if name_lower not in self.alias_to_code:
                self.alias_to_code[name_lower] = code
            # Thêm alias rút gọn
            if "kiến trúc và thiết kế phần mềm" in name_lower:
                self.alias_to_code["kiến trúc phần mềm"] = code
            elif "nhập môn an toàn, bảo mật thông tin" in name_lower:
                self.alias_to_code["an toàn mạng"] = code
                self.alias_to_code["bảo mật thông tin"] = code
            elif "lập trình mobile" in name_lower:
                self.alias_to_code["lập trình di động"] = code
            elif "trí tuệ nhân tạo" in name_lower:
                self.alias_to_code["ai"] = code
            elif "hệ điều hành" in name_lower:
                self.alias_to_code["hệ điều hành"] = code

    def is_known_code(self, code: str) -> bool:
        """Kiểm tra xem mã môn học có tồn tại trong hệ thống đào tạo không."""
        if not code:
            return False
        c_upper = code.strip().upper()
        return c_upper in self.DETAILED_COURSES or c_upper in self.CURRICULUM_COURSES

    def extract_codes(self, text: str) -> List[str]:
        """Trích xuất tất cả các chuỗi có định dạng mã môn học (FIT4201, CS50, KTTT101, XYZ999, ...)."""
        if not text:
            return []
        matches = re.findall(r"\b([A-Za-z]{2,10}\s*\d{2,4})\b", text)
        codes = []
        for m in matches:
            cleaned = re.sub(r"\s+", "", m).upper()
            if cleaned not in codes:
                codes.append(cleaned)
        return codes

    def find_unknown_entities(self, text: str) -> List[str]:
        """
        Tìm các thực thể mã môn học có trong câu nhưng KHÔNG TỒN TẠI trong cơ sở dữ liệu.
        Tuyệt đối không chạy vector search hay đoán mò với các mã này.
        """
        codes = self.extract_codes(text)
        return [c for c in codes if not self.is_known_code(c)]

    def extract_known_entities(self, text: str) -> List[str]:
        """Trích xuất danh sách các mã môn học hợp lệ đã biết từ text (cả theo code và alias)."""
        if not text:
            return []
        text_lower = text.lower()
        extracted: List[str] = []

        # 1. Tìm theo mã môn chuẩn
        codes = self.extract_codes(text)
        for c in codes:
            if self.is_known_code(c) and c not in extracted:
                extracted.append(c)

        # 2. Tìm theo tên gọi / bí danh (alias)
        sorted_aliases = sorted(self.alias_to_code.keys(), key=len, reverse=True)
        for alias in sorted_aliases:
            if len(alias) < 3:
                continue
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, text_lower):
                target_code = self.alias_to_code[alias]
                if target_code not in extracted:
                    extracted.append(target_code)

        return extracted

    def check_entity_conflict(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Phát hiện mâu thuẫn thực thể khi câu hỏi chứa đồng thời:
        - Một mã môn A (ví dụ FIT4201)
        - Và một tên/alias của môn B (ví dụ Full-Stack thuộc FIT4104)
        """
        if not text:
            return None
        text_lower = text.lower()
        codes = [c for c in self.extract_codes(text) if self.is_known_code(c)]
        if not codes:
            return None

        sorted_aliases = sorted(self.alias_to_code.keys(), key=len, reverse=True)
        for code in codes:
            code_info = self.DETAILED_COURSES.get(code) or self.CURRICULUM_COURSES.get(code, {})
            code_name = code_info.get("name", code)

            for alias in sorted_aliases:
                if len(alias) < 4:
                    continue
                alias_code = self.alias_to_code[alias]
                if alias_code == code:
                    continue

                pattern = rf"\b{re.escape(alias)}\b"
                if re.search(pattern, text_lower):
                    alias_info = self.DETAILED_COURSES.get(alias_code) or self.CURRICULUM_COURSES.get(alias_code, {})
                    alias_name = alias_info.get("name", alias)
                    return {
                        "has_conflict": True,
                        "code": code,
                        "code_name": code_name,
                        "conflicting_code": alias_code,
                        "conflicting_name": alias_name,
                        "conflicting_alias": alias,
                        "clarification_question": (
                            f"Bạn đang muốn hỏi về môn {code} ({code_name}) "
                            f"hay học phần {alias_code} ({alias_name})?"
                        ),
                        "options": [
                            f"Học phần {code} ({code_name})",
                            f"Học phần {alias_code} ({alias_name})"
                        ]
                    }

        return None

    def get_course_info(self, code: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin cơ bản của môn học."""
        if not code:
            return None
        c_upper = code.strip().upper()
        if c_upper in self.DETAILED_COURSES:
            return self.DETAILED_COURSES[c_upper]
        return self.CURRICULUM_COURSES.get(c_upper)


# Global Singleton
_entity_catalog_instance: Optional[EntityCatalog] = None


def get_entity_catalog() -> EntityCatalog:
    global _entity_catalog_instance
    if _entity_catalog_instance is None:
        _entity_catalog_instance = EntityCatalog()
    return _entity_catalog_instance
