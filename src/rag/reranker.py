# reranker.py
from sentence_transformers import CrossEncoder
from typing import List, Dict, Any

class Reranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Reranker dùng cross-encoder để xếp hạng lại các đoạn văn bản.
        """
        self.model = CrossEncoder(model_name)
    
    def rerank(self, query: str, retrieved_docs: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Xếp hạng lại các tài liệu đã retrieve.
        
        Args:
            query: câu hỏi gốc
            retrieved_docs: danh sách các dict chứa 'text' và các trường khác
            top_k: số lượng kết quả trả về sau rerank
        
        Returns:
            Danh sách các dict đã được sắp xếp lại theo điểm rerank (giảm dần)
        """
        if not retrieved_docs:
            return []
        
        # Tạo cặp (query, text) cho cross-encoder
        pairs = [(query, doc['text']) for doc in retrieved_docs]
        
        # Dự đoán điểm
        scores = self.model.predict(pairs)
        
        # Gắn điểm rerank vào mỗi doc
        for i, doc in enumerate(retrieved_docs):
            doc['rerank_score'] = float(scores[i])
        
        # Sắp xếp theo rerank_score giảm dần
        reranked = sorted(retrieved_docs, key=lambda x: x['rerank_score'], reverse=True)
        
        return reranked[:top_k]

_reranker = None

def rerank(query: str, docs: List[Dict[str, Any]], top_k: int = 15) -> List[Dict[str, Any]]:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker.rerank(query, docs, top_k)