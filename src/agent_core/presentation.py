"""
Answer Presentation Model (Round UX2):
Separates raw verified evidence extraction from user-facing presentation layout.
Enforces 100% evidence truth while providing structured, readable formatting:
- Credits: bold, prominent
- Lecturer: dedicated section
- CLO: structured numbered list (0 walls of text)
- Graduation Requirements: clean bulleted clauses
- Assessment: clean Markdown table
"""
import re
from typing import Any, Optional


def format_credits(entity: str, course_name: str, raw_value: str) -> str:
    """Format credits prominently."""
    subj = f"{course_name} ({entity})" if course_name else entity
    # Clean raw value if it has "tín chỉ" suffix already
    val = re.sub(r"(?i)\s*t[ií]n\s*ch[iỉ]", "", str(raw_value)).strip()
    return f"📌 **Số tín chỉ môn {subj}:** **{val}** tín chỉ."


def format_lecturer(entity: str, course_name: str, raw_value: str) -> str:
    """Format lecturer section cleanly."""
    subj = f"{course_name} ({entity})" if course_name else entity
    return f"👨‍🏫 **Giảng viên môn {subj}:**\n- **Cán bộ phụ trách:** {raw_value}"


def format_lecturer_email(entity: str, course_name: str, raw_value: str) -> str:
    subj = f"{course_name} ({entity})" if course_name else entity
    return f"📧 **Email giảng viên môn {subj}:** `{raw_value}`"


def format_clo(entity: str, course_name: str, raw_value: str) -> str:
    """Format CLO as a clean numbered list with bold CLO identifiers."""
    subj = f"{course_name} ({entity})" if course_name else entity
    lines = [f"🎯 **Chuẩn đầu ra (CLO) môn {subj}:**\n"]

    # Try to find CLO items like "CLO 1: ...", "CLO1: ...", "1. ..."
    items = re.findall(r"(?:CLO\s*(\d+)[:\.\-]?\s*|(?:\n|^)(\d+)[\.\)]\s*)([^\n;]+)", raw_value, re.IGNORECASE)
    if items:
        for it in items:
            num = it[0] or it[1]
            desc = it[2].strip()
            if desc:
                lines.append(f"{num}. **CLO{num}:** {desc}")
        return "\n".join(lines)

    # Split by newlines or semicolons if regular sentences
    split_items = [p.strip() for p in re.split(r"[\n;]+", raw_value) if p.strip()]
    if len(split_items) > 1:
        for idx, it in enumerate(split_items, 1):
            lines.append(f"{idx}. {it}")
        return "\n".join(lines)

    # Fallback
    return f"🎯 **Chuẩn đầu ra (CLO) môn {subj}:**\n{raw_value}"


def format_graduation(entity: str, raw_value: str) -> str:
    """Format graduation requirements as structured bullet points."""
    lines = [f"📜 **Điều kiện xét tốt nghiệp ({entity}):**\n"]
    items = [p.strip() for p in re.split(r"[\n;]+", raw_value) if p.strip()]
    if len(items) > 1:
        for it in items:
            # Clean leading bullet dashes or numbers
            clean_it = re.sub(r"^[\-\*\•\d\.\)\s]+", "", it).strip()
            if clean_it:
                lines.append(f"- {clean_it}")
        return "\n".join(lines)

    return f"📜 **Điều kiện xét tốt nghiệp ({entity}):**\n{raw_value}"


def format_assessment(entity: str, course_name: str, raw_value: str) -> str:
    """Format assessment breakdown as a clean Markdown table or key-value list."""
    subj = f"{course_name} ({entity})" if course_name else entity

    # Check if raw value contains percentage breakdowns like 10%, 40%, 50%
    has_percentages = bool(re.search(r"\d+%", raw_value))
    if has_percentages:
        table_lines = [
            f"📊 **Hình thức đánh giá môn {subj}:**\n",
            "| Thành phần đánh giá | Tỷ lệ | Hình thức / Tiêu chí |",
            "| :--- | :---: | :--- |",
        ]
        # Try to parse standard components
        parsed = False
        parts = re.split(r"[\n;]+", raw_value)
        for p in parts:
            p = p.strip()
            pct_m = re.search(r"(\d+%)", p)
            if pct_m:
                pct = pct_m.group(1)
                desc = re.sub(r"(\d+%)", "", p).strip(" -:–")
                # Detect component name
                comp = "Đánh giá học phần"
                if any(w in desc.lower() for w in ["chuyên cần", "điểm danh", "thường xuyên"]):
                    comp = "Chuyên cần / Tham gia"
                elif any(w in desc.lower() for w in ["giữa kỳ", "quá trình", "định kỳ"]):
                    comp = "Kiểm tra giữa kỳ"
                elif any(w in desc.lower() for w in ["cuối kỳ", "kết thúc"]):
                    comp = "Thi kết thúc học phần"

                table_lines.append(f"| {comp} | **{pct}** | {desc or comp} |")
                parsed = True

        if parsed:
            return "\n".join(table_lines)

    return f"📊 **Hình thức đánh giá môn {subj}:**\n{raw_value}"


def format_prerequisites(entity: str, course_name: str, raw_value: str) -> str:
    subj = f"{course_name} ({entity})" if course_name else entity
    return f"🔗 **Môn tiên quyết của {subj}:** {raw_value}."


def format_academic_warning(entity: str, raw_value: str) -> str:
    return f"⚠️ **Quy định cảnh báo học tập ({entity}):**\n{raw_value}"


def format_generic(field_vn: str, entity: str, course_name: str, raw_value: str) -> str:
    subj = f"{course_name} ({entity})" if course_name else entity
    return f"ℹ️ **Thông tin {field_vn} môn {subj}:** {raw_value}."


def format_course_card(
    entity: str,
    course_name: str,
    requirements: list,
    catalog: Optional[Any] = None,
) -> str:
    """Định dạng Student-Oriented Course Card cho Course Overview và Full Details."""
    from src.agent_core.schemas import EvidenceStatus
    valid_statuses = (EvidenceStatus.SATISFIED, EvidenceStatus.VERIFIED_VALUE, EvidenceStatus.VERIFIED_NONE)

    # Lấy tên chuẩn của môn học nếu chưa có
    c_name = course_name
    if not c_name and catalog and entity:
        c_info = catalog.get_course_info(entity)
        if c_info:
            c_name = c_info.get("canonical_name", entity)
    c_title = f"{c_name} ({entity})" if c_name and c_name != entity else entity

    field_map = {}
    unsatisfied = []
    for r in requirements:
        if r.status in valid_statuses:
            field_map[r.field] = r.extracted_value
        else:
            unsatisfied.append(r)

    sections = [f"### 📘 Thông tin học phần: **{c_title}**\n"]

    # 1. Số tín chỉ
    if "credits" in field_map:
        val = re.sub(r"(?i)\s*t[ií]n\s*ch[iỉ]", "", str(field_map["credits"])).strip()
        sections.append(f"📌 **Số tín chỉ**: **{val}** tín chỉ")

    # 2. Giảng viên & Email
    lect_text = field_map.get("lecturer")
    email_text = field_map.get("lecturer_email")
    if lect_text:
        lect_line = f"👨‍🏫 **Giảng viên**: {lect_text}"
        if email_text and email_text != lect_text:
            lect_line += f" *(Email: `{email_text}`)*"
        sections.append(lect_line)
    elif email_text:
        sections.append(f"📧 **Email giảng viên**: `{email_text}`")

    # 3. Tiên quyết
    if "prerequisites" in field_map:
        sections.append(f"📋 **Điều kiện tiên quyết**: {field_map['prerequisites']}")

    # 4. Hình thức đánh giá
    if "assessment" in field_map:
        asm_val = field_map["assessment"]
        formatted_asm = format_assessment(entity, c_name, asm_val)
        sections.append(f"\n{formatted_asm}")

    # 5. Chuẩn đầu ra (CLO)
    if "clo" in field_map:
        clo_val = field_map["clo"]
        formatted_clo = format_clo(entity, c_name, clo_val)
        sections.append(f"\n{formatted_clo}")

    # 6. Thời lượng & Kế hoạch
    hours_val = field_map.get("hours")
    plan_val = field_map.get("course_plan")
    if hours_val or plan_val:
        timing_parts = []
        if hours_val:
            timing_parts.append(f"Thời lượng: {hours_val}")
        if plan_val:
            timing_parts.append(f"Kế hoạch: {plan_val}")
        sections.append(f"⏳ **Thời lượng & Kế hoạch học tập**: {' | '.join(timing_parts)}")

    # 7. Khoa / Bộ môn phụ trách
    if "department" in field_map:
        sections.append(f"🏢 **Khoa phụ trách**: {field_map['department']}")

    # 8. Tên tiếng Anh
    if "english_name" in field_map:
        sections.append(f"🌐 **Tên tiếng Anh**: {field_map['english_name']}")

    # Báo cáo các trường chưa công bố (nếu có)
    if unsatisfied:
        field_vn_map = {
            "credits": "số tín chỉ",
            "lecturer": "giảng viên",
            "lecturer_email": "email giảng viên",
            "assessment": "hình thức đánh giá",
            "clo": "chuẩn đầu ra (CLO)",
            "hours": "số giờ học",
            "department": "khoa phụ trách",
            "english_name": "tên tiếng Anh",
            "prerequisites": "môn tiên quyết",
            "course_plan": "kế hoạch giảng dạy",
        }
        unsat_names = [field_vn_map.get(r.field, r.field) for r in unsatisfied]
        sections.append(f"\n*(Thông tin chưa được công bố trong tài liệu hiện tại: {', '.join(unsat_names)})*")

    return "\n".join(sections).strip()


def format_total_credits(data: Any) -> str:
    """Định dạng tổng số tín chỉ của chương trình đào tạo."""
    if not isinstance(data, dict):
        return f"📌 **Tổng số tín chỉ:** {data}"
    cohort = data.get("cohort", "K19")
    major = data.get("major", "Khoa học máy tính")
    total = data.get("total_credits", 0)
    semesters = data.get("semesters", [])

    lines = [
        f"🎓 **Tổng số tín chỉ CTĐT Khóa {cohort} - Ngành {major}:** **{total}** tín chỉ.\n",
        "| Học kỳ | Số tín chỉ | Số học phần |",
        "| :---: | :---: | :---: |",
    ]
    for s in semesters:
        sem_num = s.get("semester", 0)
        sem_label = f"Học kỳ {sem_num}" if sem_num > 0 else "Đại cương / Toàn trường"
        creds = s.get("semester_credits", 0)
        cnt = s.get("course_count", 0)
        lines.append(f"| {sem_label} | {creds} | {cnt} |")

    return "\n".join(lines)


def format_semester_courses(semester: Any, courses: Any, cohort: str = "K19", major: str = "Khoa học máy tính") -> str:
    """Định dạng danh sách môn học theo học kỳ thành bảng Markdown sạch sẽ."""
    if not isinstance(courses, list) or not courses:
        return f"📚 Hiện chưa có dữ liệu danh sách môn học cho Học kỳ {semester} (Khóa {cohort} - Ngành {major})."

    total_sem_credits = sum(c.get("credits", 0) for c in courses)
    lines = [
        f"📚 **Kế hoạch học tập Học kỳ {semester} (Khóa {cohort} - Ngành {major}):**\n",
        f"*(Tổng số tín chỉ trong kỳ: **{total_sem_credits}** tín chỉ)*\n",
        "| Mã HP | Tên học phần | Số tín chỉ | Tính chất |",
        "| :---: | :--- | :---: | :--- |",
    ]
    for c in courses:
        code = c.get("course_code", "")
        name = c.get("course_name", "")
        creds = c.get("credits", 0)
        c_type = c.get("course_type", "COMPULSORY")
        type_vn = "Bắt buộc" if c_type == "COMPULSORY" else ("Tự chọn" if c_type == "ELECTIVE" else ("Tốt nghiệp" if c_type == "GRADUATION" else "Đại cương"))
        lines.append(f"| `{code}` | **{name}** | {creds} | {type_vn} |")

    return "\n".join(lines)


def format_course_placement(data: Any, cohort: str = "K19", major: str = "Khoa học máy tính") -> str:
    """Định dạng vị trí học kỳ của môn học trong CTĐT."""
    if not isinstance(data, dict):
        return f"📍 Thông tin vị trí môn học: {data}"

    code = data.get("course_code", "")
    name = data.get("course_name", "")
    sem = data.get("semester")
    creds = data.get("credits", 0)

    if sem and sem > 0:
        return (
            f"📍 **Vị trí học kỳ của môn học:**\n\n"
            f"- **Học phần:** `{code}` - **{name}**\n"
            f"- **Chương trình:** Khóa **{cohort}** - Ngành **{major}**\n"
            f"- **Học kỳ bố trí:** **Học kỳ {sem}** ({creds} tín chỉ)."
        )
    return (
        f"📍 Môn học `{code}` - **{name}** ({creds} tín chỉ) thuộc nhóm học phần đại cương "
        f"hoặc tự chọn theo kế hoạch của CTĐT Khóa {cohort} - Ngành {major}."
    )


def format_curriculum_overview(courses: Any, cohort: str = "K19", major: str = "Khoa học máy tính") -> str:
    """Định dạng tổng quan danh sách môn học của CTĐT."""
    if not isinstance(courses, list) or not courses:
        return f"📋 Chưa có dữ liệu CTĐT cho Khóa {cohort} - Ngành {major}."

    total_credits = sum(c.get("credits", 0) for c in courses if c.get("course_type") != "ELECTIVE")
    lines = [
        f"📋 **Tổng quan Chương trình Đào tạo Khóa {cohort} - Ngành {major}:**\n",
        f"- **Tổng số học phần:** {len(courses)} môn\n"
        f"- **Tổng số tín chỉ:** **{total_credits}** tín chỉ\n",
        "| Học kỳ | Mã HP | Tên môn học | Tín chỉ |",
        "| :---: | :---: | :--- | :---: |",
    ]
    for c in courses[:25]:
        sem = f"Kỳ {c.get('semester', 0)}" if c.get('semester', 0) > 0 else "Đại cương"
        lines.append(f"| {sem} | `{c.get('course_code')}` | {c.get('course_name')} | {c.get('credits')} |")

    if len(courses) > 25:
        lines.append(f"\n*(Hiển thị 25/{len(courses)} học phần. Bạn có thể hỏi chi tiết từng kỳ, ví dụ: 'Kỳ 5 học những môn gì?')*")

    return "\n".join(lines)

