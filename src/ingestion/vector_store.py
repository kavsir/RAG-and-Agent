"""
Quản lý ChromaDB và Embeddings phục vụ Ingestion.
"""
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from sentence_transformers import SentenceTransformer
from src.config.settings import settings

logger = logging.getLogger(__name__)

_chroma_client_singleton: Optional[chromadb.PersistentClient] = None
_embedding_model_singleton: Optional[SentenceTransformer] = None


def get_chroma_client(persist_path: Optional[str] = None) -> chromadb.PersistentClient:
    """Lấy hoặc khởi tạo Singleton ChromaDB PersistentClient."""
    global _chroma_client_singleton
    if _chroma_client_singleton is None:
        target_path = Path(persist_path or settings.CHROMA_PATH).resolve()
        target_path.mkdir(parents=True, exist_ok=True)
        normalized_path = str(target_path.as_posix())
        _chroma_client_singleton = chromadb.PersistentClient(path=normalized_path)
        logger.info(f"ChromaDB Client khoi tao tai: {normalized_path}")
    return _chroma_client_singleton


def get_embedding_model(model_name: Optional[str] = None) -> SentenceTransformer:
    """Lấy hoặc khởi tạo Singleton SentenceTransformer embedding model."""
    global _embedding_model_singleton
    if _embedding_model_singleton is None:
        name = model_name or settings.EMBEDDING_MODEL
        logger.info(f"Dang tai embedding model: {name}")
        _embedding_model_singleton = SentenceTransformer(name)
        logger.info("Embedding model san sang.")
    return _embedding_model_singleton


class VectorStoreManager:
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.persist_directory = persist_directory or str(settings.CHROMA_PATH.as_posix())
        self.chroma_client = get_chroma_client(self.persist_directory)
        self.embedding_model = get_embedding_model(model_name or settings.EMBEDDING_MODEL)

    def get_or_create_collection(self, collection_name: str):
        return self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 400,
                "hnsw:M": 64,
                "hnsw:search_ef": 200,
            },
        )

    def delete_collection(self, collection_name: str):
        try:
            self.chroma_client.delete_collection(collection_name)
            logger.info(f"Da xoa collection: {collection_name}")
        except Exception:
            pass

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self.embedding_model.encode(texts, normalize_embeddings=True).tolist()

    def add_documents(self, collection_name: str, chunks: List[Dict[str, Any]]):
        """Thêm tài liệu vào collection."""
        if not chunks:
            return 0
        collection = self.get_or_create_collection(collection_name)
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]
        ids = [chunk.get("id") or str(uuid.uuid4()) for chunk in chunks]

        # Batching embeddings để tránh tràn bộ nhớ
        batch_size = 64
        for i in range(0, len(chunks), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_metadatas = metadatas[i : i + batch_size]
            batch_ids = ids[i : i + batch_size]
            batch_embeddings = self.embed_texts(batch_texts)

            collection.add(
                documents=batch_texts,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                ids=batch_ids,
            )
        logger.info(f"Da them {len(chunks)} chunks vao collection '{collection_name}'")
        return len(chunks)

    def get_collection_stats(self, collection_name: str) -> int:
        try:
            collection = self.chroma_client.get_collection(collection_name)
            return collection.count()
        except Exception:
            return 0
