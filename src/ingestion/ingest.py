import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from pathlib import Path
from tqdm import tqdm
from src.ingestion.loaders import load_docx
from src.ingestion.metadata_builder import detect_doc_type, build_metadata
from src.ingestion.chunkers import chunk_document
from src.ingestion.vector_store import VectorStoreManager

# Chuẩn hóa đường dẫn Windows - dùng pathlib.Path
_RAW_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data_raw"
RAW_DATA_PATH = str(_RAW_DATA_PATH.as_posix())

_VECTOR_STORE_PATH = Path(__file__).resolve().parent.parent.parent / "vector_store"
VECTOR_STORE_PATH = str(_VECTOR_STORE_PATH.as_posix())
def main():
    vs_manager = VectorStoreManager(persist_directory=VECTOR_STORE_PATH)
    
    all_files = []
    for root, dirs, files in os.walk(RAW_DATA_PATH):
        for file in files:
            if file.endswith('.docx') or file.endswith('.txt'):
                all_files.append(os.path.join(root, file))
    
    for file_path in tqdm(all_files, desc="Xử lý files"):
        print(f"\n📄 Đang xử lý: {file_path}")
        text = load_docx(file_path)
        if not text:
            continue
        
        doc_type = detect_doc_type(file_path)
        collection_map = {
            'syllabus': 'course_detail',
            'curriculum': 'curriculum',
            'regulation': 'regulation',
            'unknown': 'others'
        }
        collection_name = collection_map.get(doc_type, 'others')
        
        chunked = chunk_document(text, doc_type)
        chunks_to_add = []
        for i, (chunk_text, extra_meta) in enumerate(chunked):
            if not chunk_text.strip():
                continue
            chunk_id = f"{os.path.basename(file_path)}_chunk{i}"
            metadata = build_metadata(file_path, chunk_text, chunk_id, doc_type=doc_type, **extra_meta)
            metadata.update(extra_meta)
            chunks_to_add.append({
                "text": chunk_text,
                "metadata": metadata
            })
        
        vs_manager.add_documents(collection_name, chunks_to_add)
    
    print("\n📊 Thống kê các collection:")
    for col in ['course_detail', 'curriculum', 'regulation', 'others']:
        count = vs_manager.get_collection_stats(col)
        print(f"  - {col}: {count} chunks")

if __name__ == "__main__":
    main()