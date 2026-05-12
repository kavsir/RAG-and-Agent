from pathlib import Path
from src.rag.hybrid_retriever import HybridRetriever

# Chuẩn hóa đường dẫn Windows
_VECTOR_STORE = Path(__file__).resolve().parent / "vector_store"
VECTOR_STORE_PATH = str(_VECTOR_STORE.as_posix())

retriever = HybridRetriever(
    persist_directory=VECTOR_STORE_PATH,
    collection_name="course_detail"
)
docs = retriever.retrieve("giảng viên Hệ thống nhúng", top_k=30)
for doc in docs:
    if "II. Thông tin giảng viên" in doc['text']:
        print("✅ Found teacher info chunk")
        print(doc['text'][:500])
        break
else:
    print("❌ Not found")