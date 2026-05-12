# chunkers.py
import re
from typing import List, Tuple
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ==================== UTILITIES ====================
def clean_text(text: str) -> str:
    """Loại bỏ các ký tự markdown không cần thiết (**, *, #) nhưng giữ nội dung."""
    # Xóa các dấu ** bao quanh từ/cụm từ
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    # Xóa các dấu # đầu dòng (nếu có)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    return text

def split_by_paragraphs(text: str) -> List[Tuple[str, dict]]:
    """Fallback: chunk theo đoạn văn."""
    paragraphs = text.split('\n\n')
    return [(p.strip(), {"type": "paragraph"}) for p in paragraphs if p.strip()]

def extract_clos(text: str) -> List[str]:
    """Trích xuất danh sách CLO từ nội dung."""
    pattern = r'CLO\s*\d+\s*[:.]'
    matches = re.findall(pattern, text, re.IGNORECASE)
    if matches:
        return [m.strip() for m in matches]
    return []

# ==================== SYLLABUS ====================
def split_syllabus(text: str) -> List[Tuple[str, dict]]:
    """
    Tách syllabus thành các chunk theo các mục I, II, III, IV, V, VI, VII, VIII, IX.
    Với mục VII (Kế hoạch giảng dạy) sẽ tách theo tuần.
    Với mục VIII (Đánh giá học phần) sẽ tách các phần con.
    """
    text = clean_text(text)
    # Pattern nhận diện heading: I., II., III., ...
    heading_pattern = re.compile(r'^([IVX]+)\.\s+(.+)', re.MULTILINE)
    matches = list(heading_pattern.finditer(text))
    if not matches:
        return split_by_paragraphs(text)
    
    chunks = []
    for i, match in enumerate(matches):
        heading_num = match.group(1)
        heading_title = match.group(2)
        heading = f"{heading_num}. {heading_title}"
        start = match.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        chunk_text = text[start:end].strip()
        
        extra = {
            "section": heading,
            "section_num": heading_num,
            "section_title": heading_title,
            "type": "section"
        }
        
        # Xử lý riêng cho từng mục
        if heading_num == 'V':
            clos = extract_clos(chunk_text)
            extra["clos"] = clos
            extra["type"] = "clos"
        elif heading_num == 'I':
            extra["type"] = "general_info"
        elif heading_num == 'II':
            extra["type"] = "lecturers"
        elif heading_num == 'III':
            extra["type"] = "description"
        elif heading_num == 'IV':
            extra["type"] = "objectives"
        elif heading_num == 'VI':
            extra["type"] = "materials"
        elif heading_num == 'VII':
            # Tách nhỏ phần kế hoạch giảng dạy theo tuần
            week_chunks = split_by_weeks_in_section(chunk_text)
            if week_chunks:
                for wc_text, wc_extra in week_chunks:
                    # Gắn thêm thông tin mục VII
                    wc_extra.update({
                        "section": heading,
                        "section_num": heading_num,
                        "section_title": heading_title,
                    })
                    chunks.append((wc_text, wc_extra))
            else:
                # Nếu không tách được theo tuần, vẫn giữ nguyên
                chunks.append((chunk_text, extra))
            continue  # đã xử lý xong, không thêm chunk gốc
        elif heading_num == 'VIII':
            # Tách nhỏ phần đánh giá
            sub_chunks = split_assessment(chunk_text, heading, heading_num)
            if sub_chunks:
                chunks.extend(sub_chunks)
            else:
                chunks.append((chunk_text, extra))
            continue
        elif heading_num == 'IX':
            extra["type"] = "regulation"
        
        # Các mục không xử lý đặc biệt
        chunks.append((chunk_text, extra))
    
    return chunks

def split_by_weeks_in_section(text: str) -> List[Tuple[str, dict]]:
    """
    Tách phần kế hoạch giảng dạy thành các chunk theo tuần.
    Nhận diện các dạng: "Tuần 1", "Tuần 1-2", "Tuần 1 đến tuần 2"
    """
    # Pattern bắt các dạng: "Tuần 1", "Tuần 1-2", "Tuần 1 đến tuần 2",...
    week_pattern = r'(Tuần\s+\d+(?:\s*(?:đến|-)\s*\d+)?)[\s:–—-]+'
    splits = re.split(week_pattern, text, flags=re.IGNORECASE)
    chunks = []
    current_week = None
    for i, segment in enumerate(splits):
        if i % 2 == 1:
            current_week = segment.strip()
        else:
            if current_week and segment.strip():
                chunk_text = current_week + "\n" + segment.strip()
                extra = {"week": current_week, "type": "week"}
                chunks.append((chunk_text, extra))
            elif segment.strip():
                chunks.append((segment.strip(), {"type": "week_intro"}))
    return chunks

def split_assessment(text: str, parent_heading: str, parent_num: str) -> List[Tuple[str, dict]]:
    """
    Tách phần Đánh giá học phần (mục VIII) thành các chunk con:
    - 8.1. Nội dung đánh giá
    - 8.2. Tiêu chí đánh giá
        - a) Chi tiết đánh giá chuyên cần
        - b) Chi tiết đánh giá Bài kiểm tra giữa kỳ
        - c) Chi tiết đánh giá Bài thi kết thúc học phần
    """
    # Các tiêu đề cấp 2: 8.1, 8.2, ...
    sub_heading_pattern = re.compile(r'^(\d+\.\d+)\s+(.+)', re.MULTILINE)
    # Các tiêu đề cấp 3: a), b), c) ...
    sub_sub_pattern = re.compile(r'^([a-z]\))\s+(.+)', re.MULTILINE)
    
    matches = list(sub_heading_pattern.finditer(text))
    if not matches:
        return []
    
    chunks = []
    for i, match in enumerate(matches):
        sub_num = match.group(1)
        sub_title = match.group(2)
        start = match.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        chunk_text = text[start:end].strip()
        
        # Kiểm tra xem trong chunk này có các mục con a), b), c) không
        sub_sub_matches = list(sub_sub_pattern.finditer(chunk_text))
        if sub_sub_matches:
            # Tách tiếp các mục con
            for j, subm in enumerate(sub_sub_matches):
                sub_sub_id = subm.group(1)
                sub_sub_title = subm.group(2)
                sub_start = subm.start()
                sub_end = sub_sub_matches[j+1].start() if j+1 < len(sub_sub_matches) else len(chunk_text)
                sub_chunk = chunk_text[sub_start:sub_end].strip()
                extra = {
                    "section": f"{parent_heading} - {sub_num} {sub_title}",
                    "section_num": parent_num,
                    "sub_section": sub_sub_id,
                    "sub_section_title": sub_sub_title,
                    "type": "assessment_sub"
                }
                chunks.append((sub_chunk, extra))
        else:
            extra = {
                "section": f"{parent_heading} - {sub_num} {sub_title}",
                "section_num": parent_num,
                "type": "assessment"
            }
            chunks.append((chunk_text, extra))
    
    return chunks

# ==================== CURRICULUM ====================
def split_curriculum(text: str) -> List[Tuple[str, dict]]:
    """
    Tách curriculum thành các phần riêng biệt:
    - Header (khóa, ngành)
    - Các học kỳ (HỌC KỲ X)
    - Các chuyên ngành (CHUYÊN NGÀNH ...)
    - Thực tập và tốt nghiệp
    - Các học phần theo kế hoạch nhà trường
    - Danh sách học phần lựa chọn
    """
    # Sử dụng pattern tương tự như cũ (bạn có thể giữ nguyên)
    chunks = []
    lines = text.split('\n')
    current_section = []
    current_type = None
    current_metadata = {}
    
    header_pattern = re.compile(r'^#+\s*(.+)')
    semester_pattern = re.compile(r'^(HỌC KỲ\s+\d+)', re.IGNORECASE)
    specialization_pattern = re.compile(r'^(CHUYÊN NGÀNH\s+.+)', re.IGNORECASE)
    internship_pattern = re.compile(r'^(THỰC TẬP VÀ TỐT NGHIỆP)', re.IGNORECASE)
    uni_plan_pattern = re.compile(r'^(CÁC HỌC PHẦN THEO KẾ HOẠCH CỦA NHÀ TRƯỜNG)', re.IGNORECASE)
    elective_pattern = re.compile(r'^(DANH SÁCH HỌC PHẦN LỰA CHỌN)', re.IGNORECASE)
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if semester_pattern.match(line):
            if current_section:
                chunks.append(('\n'.join(current_section), current_metadata))
            current_section = [line]
            current_type = 'semester'
            current_metadata = {'type': 'semester', 'semester': line.strip()}
        elif specialization_pattern.match(line):
            if current_section:
                chunks.append(('\n'.join(current_section), current_metadata))
            current_section = [line]
            current_type = 'specialization'
            current_metadata = {'type': 'specialization', 'specialization': line.strip()}
        elif internship_pattern.match(line):
            if current_section:
                chunks.append(('\n'.join(current_section), current_metadata))
            current_section = [line]
            current_type = 'internship'
            current_metadata = {'type': 'internship'}
        elif uni_plan_pattern.match(line):
            if current_section:
                chunks.append(('\n'.join(current_section), current_metadata))
            current_section = [line]
            current_type = 'uni_plan'
            current_metadata = {'type': 'uni_plan'}
        elif elective_pattern.match(line):
            if current_section:
                chunks.append(('\n'.join(current_section), current_metadata))
            current_section = [line]
            current_type = 'elective_list'
            current_metadata = {'type': 'elective_list'}
        elif header_pattern.match(line) and not current_section:
            current_section = [line]
            current_type = 'header'
            current_metadata = {'type': 'header'}
        else:
            if current_section is not None:
                current_section.append(line)
            else:
                current_section = [line]
                current_type = 'header'
                current_metadata = {'type': 'header'}
    
    if current_section:
        chunks.append(('\n'.join(current_section), current_metadata))
    
    return chunks

# ==================== REGULATION ====================
def split_regulation(text: str) -> List[Tuple[str, dict]]:
    """Tách regulation theo Điều."""
    pattern = r'(Điều\s+\d+[\.:])'
    splits = re.split(pattern, text)
    chunks = []
    current_article = None
    for i, segment in enumerate(splits):
        if i % 2 == 1:
            current_article = segment.strip()
        else:
            if current_article and segment.strip():
                chunk_text = current_article + "\n" + segment.strip()
                extra = {"article": current_article, "type": "article"}
                chunks.append((chunk_text, extra))
            elif segment.strip():
                # Phần đầu (quyết định ban hành)
                chunks.append((segment.strip(), {"type": "header"}))
    return chunks

# ==================== MAIN ====================
def chunk_document(text: str, doc_type: str) -> List[Tuple[str, dict]]:
    if doc_type == 'syllabus':
        return split_syllabus(text)
    elif doc_type == 'curriculum':
        return split_curriculum(text)
    elif doc_type == 'regulation':
        return split_regulation(text)
    else:
        splitter = RecursiveCharacterTextSplitter(chunk_size=1080, chunk_overlap=50)
        chunks = splitter.split_text(text)
        return [(chunk, {}) for chunk in chunks]