# src/cache/semantic_cache.py
import numpy as np
from pathlib import Path
from typing import Optional
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import uuid
import os

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
        print(f"✅ ChromaDB Cache Client initialized at: {normalized_path}")
    return _chroma_client_singleton

class SemanticCache:
    """
    Semantic cache dùng ChromaDB để lưu trữ câu hỏi và câu trả lời.
    Khi có câu hỏi mới, tính embedding và tìm trong DB những câu hỏi tương tự.
    Nếu độ tương đồng vượt ngưỡng, trả về câu trả lời đã lưu.
    """
    def __init__(self, 
                 persist_directory="D:/Agent_AI_Levelup/Agent_AI_Levelup/vector_cache",
                 collection_name: str = "semantic_cache",
                 model_name: str = "all-MiniLM-L6-v2",
                 similarity_threshold: float = 0.98):
        
        # Chuẩn hóa đường dẫn Windows
        self.persist_directory_path = Path(persist_directory).resolve()
        self.persist_directory_path.mkdir(parents=True, exist_ok=True)
        self.persist_directory = str(self.persist_directory_path.as_posix())
        
        self.collection_name = collection_name
        self.similarity_threshold = similarity_threshold
        
        # Sử dụng Singleton client
        self.chroma_client = get_chroma_client(self.persist_directory)
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        # Load embedding model (dùng chung với RAG)
        self.embedding_model = SentenceTransformer(model_name)
    
    def _compute_embedding(self, text: str) -> list:
        """Tính embedding cho một câu hỏi."""
        emb = self.embedding_model.encode(text, normalize_embeddings=True)
        return emb.tolist()
    
    def get(self, query: str) -> Optional[str]:
        """
        Tìm trong cache câu hỏi tương tự với query.
        Nếu tìm thấy, trả về câu trả lời; nếu không, trả về None.
        """
        query_emb = self._compute_embedding(query)
        
        # Tìm top 1 kết quả gần nhất
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=1,
            include=["documents", "distances", "metadatas"]
        )
        
        if not results['ids'][0]:
            return None
        
        # Khoảng cách cosine (càng nhỏ càng gần), similarity = 1 - distance
        distance = results['distances'][0][0]
        similarity = 1 - distance
        
        if similarity >= self.similarity_threshold:
            # Trả về câu trả lời đã lưu
            return results['documents'][0][0]
        else:
            return None
    
    def set(self, query: str, answer: str):
        """
        Lưu cặp (câu hỏi, câu trả lời) vào cache.
        """
        query_emb = self._compute_embedding(query)
        doc_id = str(uuid.uuid4())
        
        self.collection.add(
            documents=[answer],
            embeddings=[query_emb],
            ids=[doc_id],
            metadatas=[{"query": query}]  # lưu câu hỏi gốc để debug
        )
        
    def clear(self):
        """Xóa toàn bộ cache (dùng khi cần reset)."""
        self.chroma_client.delete_collection(self.collection_name)
        self.collection = self.chroma_client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )