# src/cache/memory_cache.py
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import Optional, List, Tuple
import hashlib

class InMemorySemanticCache:
    def __init__(self, model_name='BAAI/bge-m3', threshold=0.85, max_size=1000):
        self.model = SentenceTransformer(model_name)
        self.threshold = threshold
        self.max_size = max_size
        self.cache: List[Tuple[np.ndarray, str]] = []  # (embedding, answer)
    
    def _embed(self, text: str):
        return self.model.encode(text, normalize_embeddings=True)
    
    def get(self, query: str) -> Optional[str]:
        query_emb = self._embed(query)
        for emb, answer in self.cache:
            sim = np.dot(query_emb, emb)
            if sim >= self.threshold:
                return answer
        return None
    
    def set(self, query: str, answer: str):
        if len(self.cache) >= self.max_size:
            # Xóa cái cũ nhất (FIFO)
            self.cache.pop(0)
        query_emb = self._embed(query)
        self.cache.append((query_emb, answer))