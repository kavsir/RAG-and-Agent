import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from src.rag.hybrid_retriever import HybridRetriever

DEBUG = False

# Chuẩn hóa đường dẫn Windows - dùng pathlib.Path
_VECTOR_STORE_PATH = Path(__file__).resolve().parent.parent.parent / "vector_store"
VECTOR_STORE_PATH = str(_VECTOR_STORE_PATH.as_posix())

INTENT_TO_COLLECTION = {
    "lecturer_info": "course_detail",
    "course_info_basic": "course_detail",
    "course_info_full": "course_detail",
    "course_plan": "curriculum",
    "regulation": "regulation",
    "grade_inquiry": "course_detail",
    "schedule": "curriculum",
    "greeting": None,
    "general_question": None,
    "set_reminder": None,
    "send_email": None,
    "course_information": "course_detail"
}

_retrievers = {}

def get_retriever(collection_name: str) -> HybridRetriever:
    if collection_name not in _retrievers:
        _retrievers[collection_name] = HybridRetriever(
            persist_directory=VECTOR_STORE_PATH,
            collection_name=collection_name,
            alpha=0.7
        )
    return _retrievers[collection_name]

def retrieve_docs(
    query: str,
    intent: Optional[str] = None,
    top_k: int = 10,
    filter_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    if DEBUG:
        print(f"🔍 retrieve_docs() called with query='{query}', intent={intent}, top_k={top_k}, filter_type={filter_type}")

    # Xác định collection dựa trên intent
    collection_name = None
    if intent and intent in INTENT_TO_COLLECTION:
        collection_name = INTENT_TO_COLLECTION[intent]
    else:
        # fallback: search tất cả
        all_docs = []
        for col in ["course_detail", "curriculum", "regulation"]:
            retriever = get_retriever(col)
            docs = retriever.retrieve(query, top_k=top_k // 2)
            all_docs.extend(docs)
        all_docs.sort(key=lambda x: x['score'], reverse=True)
        return all_docs[:top_k]

    # Nếu xác định được collection
    retriever = get_retriever(collection_name)
    if filter_type:
        filter_metadata = {"chunk_type": filter_type}
        return retriever.retrieve(query, top_k=top_k, filter_metadata=filter_metadata)
    else:
        return retriever.retrieve(query, top_k=top_k)