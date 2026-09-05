"""
Vector Memory: Lưu trữ ngữ cảnh ngữ nghĩa lịch sử câu hỏi vào ChromaDB runtime.
"""
import uuid
import logging
from typing import List
from src.ingestion.vector_store import get_chroma_client, get_embedding_model

logger = logging.getLogger(__name__)


class VectorMemory:
    def __init__(self):
        self.chroma_client = get_chroma_client()
        try:
            self.collection = self.chroma_client.get_or_create_collection(
                name="user_memory",
                metadata={"hnsw:space": "cosine"},
            )
            self.embedding_model = get_embedding_model()
        except Exception as e:
            logger.warning(f"Khong the khoi tao VectorMemory: {e}")
            self.collection = None
            self.embedding_model = None

    def add_memory(self, text: str):
        if not self.collection or not self.embedding_model:
            return
        try:
            emb = self.embedding_model.encode(text, normalize_embeddings=True).tolist()
            self.collection.add(
                documents=[text],
                embeddings=[emb],
                ids=[str(uuid.uuid4())],
            )
        except Exception as e:
            logger.error(f"Loi them vector memory: {e}")

    def search_memory(self, query: str, k: int = 3) -> List[str]:
        if not self.collection or not self.embedding_model:
            return []
        try:
            emb = self.embedding_model.encode(query, normalize_embeddings=True).tolist()
            res = self.collection.query(query_embeddings=[emb], n_results=k)
            if res and res.get("documents") and res["documents"][0]:
                return res["documents"][0]
            return []
        except Exception as e:
            logger.error(f"Loi tim kiem vector memory: {e}")
            return []
