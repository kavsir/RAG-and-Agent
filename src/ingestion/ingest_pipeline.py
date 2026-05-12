import os
import re
from uuid import uuid4

import chromadb
from docx import Document

from llama_index.embeddings.huggingface import HuggingFaceEmbedding


# =========================
# CONFIG
# =========================

VECTOR_PATH = "vector_store"

CURRICULUM_FOLDER = "data_raw/curriculum"
COURSE_FOLDER = "data_raw/course_detail"
REGULATION_FOLDER = "data_raw/regulation"


# =========================
# EMBEDDING MODEL
# =========================

embed_model = HuggingFaceEmbedding(
    model_name="BAAI/bge-m3"
)


# =========================
# CHROMA CLIENT
# =========================

client = chromadb.PersistentClient(path=VECTOR_PATH)


# =========================
# RESET COLLECTION
# =========================

def reset_collections():

    print("Reset collections...")

    try:
        client.delete_collection("course_db")
    except:
        pass

    try:
        client.delete_collection("curriculum_db")
    except:
        pass

    try:
        client.delete_collection("regulation_db")
    except:
        pass


# =========================
# CREATE COLLECTION
# =========================

def create_collections():

    global course_collection
    global curriculum_collection
    global reg_collection

    course_collection = client.get_or_create_collection("course_db")

    curriculum_collection = client.get_or_create_collection("curriculum_db")

    reg_collection = client.get_or_create_collection("regulation_db")


# =========================
# READ DOCX
# =========================

def read_docx(path):

    doc = Document(path)

    lines = []

    for p in doc.paragraphs:

        text = p.text.strip()

        if text:
            lines.append(text)

    return lines


# =========================
# GET ALL DOCX
# =========================

def get_all_docx(folder):

    files = []

    if not os.path.exists(folder):
        return files

    for f in os.listdir(folder):

        if f.endswith(".docx"):

            files.append(os.path.join(folder, f))

    return files


# =========================
# CHUNK BY SECTION
# =========================

def chunk_by_section(lines):

    chunks = []

    current = []

    for line in lines:

        if re.match(r"^[IVX]+\.", line):

            if current:

                chunks.append(" ".join(current))

                current = []

        current.append(line)

    if current:

        chunks.append(" ".join(current))

    return chunks


# =========================
# INGEST CURRICULUM
# =========================

def ingest_curriculum(file):

    print("Ingest curriculum:", file)

    lines = read_docx(file)

    semester = None

    pattern = r"([A-Z]{3,4}\d{4})\s*-\s*(.*?)\s*-\s*(\d+)\s*tín chỉ"

    texts = []
    metadatas = []
    ids = []

    for line in lines:

        if "HỌC KỲ" in line.upper():

            semester = line.split()[-1]

        match = re.search(pattern, line)

        if match:

            code = match.group(1)
            name = match.group(2)
            credits = match.group(3)

            texts.append(line)

            metadatas.append({
                "document_type": "curriculum",
                "course_code": code,
                "course_name": name,
                "credits": credits,
                "semester": semester
            })

            ids.append(str(uuid4()))

    if texts:

        embeddings = embed_model.get_text_embedding_batch(texts)

        curriculum_collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )


# =========================
# INGEST COURSE DETAIL
# =========================

def ingest_course_detail(file):

    print("Ingest course:", file)

    lines = read_docx(file)

    code = ""
    name = ""

    for line in lines:

        if "Mã học phần" in line:

            code = line.split(":")[-1].strip()

        if "Tên học phần" in line:

            name = line.split(":")[-1].strip()

    chunks = chunk_by_section(lines)

    texts = []
    metadatas = []
    ids = []

    for i, chunk in enumerate(chunks):

        texts.append(chunk)

        metadatas.append({
            "document_type": "course_detail",
            "course_code": code,
            "course_name": name,
            "section": f"section_{i}"
        })

        ids.append(f"{code}_{i}")

    if texts:

        embeddings = embed_model.get_text_embedding_batch(texts)

        course_collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )


# =========================
# INGEST REGULATION
# =========================

def ingest_regulation(file):

    print("Ingest regulation:", file)

    lines = read_docx(file)

    texts = []
    metadatas = []
    ids = []

    for i, line in enumerate(lines):

        if len(line) < 40:
            continue

        texts.append(line)

        metadatas.append({
            "document_type": "regulation",
            "type": "academic_policy"
        })

        ids.append(f"REG_{i}_{uuid4()}")

    if texts:

        embeddings = embed_model.get_text_embedding_batch(texts)

        reg_collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )


# =========================
# RUN INGEST
# =========================

def run_ingest():

    print("\n===== START INGEST =====\n")

    curriculum_files = get_all_docx(CURRICULUM_FOLDER)

    for file in curriculum_files:

        ingest_curriculum(file)


    course_files = get_all_docx(COURSE_FOLDER)

    for file in course_files:

        ingest_course_detail(file)


    regulation_files = get_all_docx(REGULATION_FOLDER)

    for file in regulation_files:

        ingest_regulation(file)


    print("\n===== INGEST DONE =====\n")


# =========================
# MAIN
# =========================

if __name__ == "__main__":

    reset_collections()

    create_collections()

    run_ingest()