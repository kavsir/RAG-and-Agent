# test_full_pipeline.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from pathlib import Path
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.reranker import Reranker
from src.rag.response_generator import generate_response

def main():
    # Chuẩn hóa đường dẫn Windows
    _VECTOR_STORE = Path(__file__).resolve().parent.parent.parent / "vector_store"
    VECTOR_STORE_PATH = str(_VECTOR_STORE.as_posix())
    
    # Chọn collection cần query
    collection_name = "course_detail"  # hoặc "curriculum", "regulation"
    
    retriever = HybridRetriever(
        persist_directory=VECTOR_STORE_PATH,
        collection_name=collection_name,
        alpha=0.7
    )
    reranker = Reranker()
    
    # Query mẫu
    query = "Môn Hệ thống nhúng có bao nhiêu tín chỉ , mã học phần, chi tiết học phần, Thông tin giảng viên, Tóm tắt nội dung học phần, Mục tiêu của học phần, Chuẩn đầu ra học phần?"
    
    # Bước 1: Retrieve
    print(f"🔍 Query: {query}")
    results = retriever.retrieve(query, top_k=10)
    print(f"📥 Retrieved {len(results)} documents từ hybrid search.")
    
    # Bước 2: Rerank
    reranked = reranker.rerank(query, results, top_k=5)
    print(f"🔄 Reranked, giữ lại {len(reranked)} documents.")
    
    # Bước 3: Generate response
    print("🤖 Đang sinh câu trả lời...")
    answer = generate_response(query, reranked, student_profile=None)
    
    print("\n📝 Câu trả lời:")
    print(answer)

if __name__ == "__main__":
    main()