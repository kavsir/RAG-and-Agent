# vector_store.py
import chromadb
from sentence_transformers import SentenceTransformer
import os
from pathlib import Path
from typing import List, Dict, Any
import uuid

# Singleton ChromaDB Client để tránh lỗi tranh chấp tài nguyên
_chroma_client_singleton = None

def get_chroma_client(persist_path: str) -> chromadb.PersistentClient:
    """Lấy hoặc khởi tạo ChromaDB client duy nhất (Singleton)."""
    global _chroma_client_singleton
    if _chroma_client_singleton is None:
        # Chuẩn hóa đường dẫn
        path_obj = Path(persist_path).resolve()
        path_obj.mkdir(parents=True, exist_ok=True)
        normalized_path = str(path_obj.as_posix())
        _chroma_client_singleton = chromadb.PersistentClient(path=normalized_path)
        print(f"✅ ChromaDB Client initialized at: {normalized_path}")
    return _chroma_client_singleton

class VectorStoreManager:
    def __init__(self, persist_directory: str, model_name: str = "BAAI/bge-m3"):
        # Chuẩn hóa đường dẫn Windows
        self.persist_directory_path = Path(persist_directory).resolve()
        self.persist_directory_path.mkdir(parents=True, exist_ok=True)
        self.persist_directory = str(self.persist_directory_path.as_posix())
        
        # Sử dụng Singleton client
        self.chroma_client = get_chroma_client(self.persist_directory)
        self.embedding_model = SentenceTransformer(model_name)

    def get_or_create_collection(self, collection_name: str):
        return self.chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 400,   # tăng từ 200 lên 400 (chính xác hơn)
            "hnsw:M": 64,                  # tăng từ 32 lên 64 (chính xác hơn)
            "hnsw:search_ef": 200          # tìm kiếm với 200 điểm lân cận
        }
    )
    

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return self.embedding_model.encode(texts, normalize_embeddings=True).tolist()

    def add_documents(self, collection_name: str, chunks: List[Dict[str, Any]]):
        """
        chunks: list of dict với các key: text, metadata
        """
        if not chunks:
            return
        collection = self.get_or_create_collection(collection_name)
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]
        ids = [str(uuid.uuid4()) for _ in chunks]
        embeddings = self.embed_texts(texts)
        collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        print(f"✅ Đã thêm {len(chunks)} chunk vào collection '{collection_name}'.")

    def get_collection_stats(self, collection_name: str):
        collection = self.get_or_create_collection(collection_name)
        return collection.count()