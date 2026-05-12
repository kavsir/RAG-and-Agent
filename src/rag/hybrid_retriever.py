# hybrid_retriever.py
import os
import pickle
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
import chromadb

DEBUG = False

# Chuẩn hóa đường dẫn Windows - dùng pathlib.Path
_VECTOR_STORE_PATH = Path(__file__).resolve().parent.parent.parent / "vector_store"
VECTOR_STORE_PATH = str(_VECTOR_STORE_PATH.as_posix())

# Singleton ChromaDB Client để tránh lỗi tranh chấp tài nguyên 'bindings'
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

class HybridRetriever:
    def __init__(
        self,
        persist_directory: str,
        collection_name: str,
        model_name: str = "BAAI/bge-m3",
        bm25_k1: float = 1.5,
        bm25_b: float = 0.75,
        alpha: float = 0.75,
    ):
        # Chuẩn hóa persist_directory bằng pathlib
        self.persist_directory_path = Path(persist_directory).resolve()
        self.persist_directory_path.mkdir(parents=True, exist_ok=True)
        self.persist_directory = str(self.persist_directory_path.as_posix())
        
        self.collection_name = collection_name
        self.alpha = alpha
        self.bm25_k1 = bm25_k1
        self.bm25_b = bm25_b

        # Sử dụng Singleton client
        self.chroma_client = get_chroma_client(self.persist_directory)
        try:
            self.collection = self.chroma_client.get_collection(collection_name)
        except Exception as e:
            raise ValueError(f"Collection '{collection_name}' không tồn tại hoặc lỗi: {e}")

        # Load embedding model
        self.embedding_model = SentenceTransformer(model_name)

        # Xây dựng hoặc load BM25 index
        self.bm25_index = None
        self.bm25_corpus = None
        self.bm25_doc_ids = None
        self._load_or_build_bm25()

    def _load_or_build_bm25(self):
        """Tải BM25 index từ file nếu có, nếu không thì xây dựng mới."""
        bm25_path = self.persist_directory_path / f"bm25_{self.collection_name}.pkl"
        
        if bm25_path.exists():
            with open(str(bm25_path), 'rb') as f:
                data = pickle.load(f)
                self.bm25_index = data['index']
                self.bm25_corpus = data['corpus']
                self.bm25_doc_ids = data['doc_ids']
            print(f"✅ Đã tải BM25 index cho collection '{self.collection_name}' từ file.")
            return

        # Xây dựng mới
        print(f"🔄 Đang xây dựng BM25 index cho collection '{self.collection_name}'...")
        all_docs = self.collection.get(include=['documents'])
        texts = all_docs.get('documents', [])
        ids = all_docs.get('ids', [])

        if not texts:
            print(f"⚠️ Collection '{self.collection_name}' không có document nào, bỏ qua BM25.")
            self.bm25_index = None
            self.bm25_corpus = []
            self.bm25_doc_ids = []
            return

        # Tokenize đơn giản (tách từ bằng khoảng trắng)
        tokenized_corpus = [text.lower().split() for text in texts]

        self.bm25_index = BM25Okapi(tokenized_corpus, k1=self.bm25_k1, b=self.bm25_b)
        self.bm25_corpus = texts
        self.bm25_doc_ids = ids

        # Lưu lại
        with open(str(bm25_path), 'wb') as f:
            pickle.dump({
                'index': self.bm25_index,
                'corpus': self.bm25_corpus,
                'doc_ids': self.bm25_doc_ids
            }, f)
        print(f"✅ Đã xây dựng và lưu BM25 index cho collection '{self.collection_name}'.")

    def retrieve(self, query: str, top_k: int = 10, filter_metadata: Optional[Dict] = None) -> List[Dict[str, Any]]:
        if DEBUG: print(f"🚀 HybridRetriever.retrieve() on {self.collection_name} with query: {query}")
    # ... phần còn lại
        """Truy vấn hybrid, trả về top_k kết quả kèm điểm số."""
        # 1. Vector search
        query_embedding = self.embedding_model.encode([query], normalize_embeddings=True).tolist()[0]
        vector_results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k * 2,
            where=filter_metadata
        )

        vector_scores = {}
        if vector_results['ids'] and vector_results['ids'][0]:
            for i, doc_id in enumerate(vector_results['ids'][0]):
                distance = vector_results['distances'][0][i]
                vector_scores[doc_id] = 1.0 / (1.0 + distance)

        # 2. BM25 search (nếu có index)
        bm25_scores = []
        if self.bm25_index:
            tokenized_query = query.lower().split()
            bm25_scores = self.bm25_index.get_scores(tokenized_query)
            # Chuẩn hóa về [0,1]
            if max(bm25_scores) > 0:
                bm25_scores = bm25_scores / max(bm25_scores)
        else:
            bm25_scores = [0.0] * len(self.bm25_doc_ids)

        bm25_map = {}
        for idx, doc_id in enumerate(self.bm25_doc_ids):
            bm25_map[doc_id] = bm25_scores[idx] if idx < len(bm25_scores) else 0.0

        # 3. Kết hợp điểm
        all_ids = set(vector_scores.keys()) | set(bm25_map.keys())
        combined_scores = []

        # Lấy thông tin chi tiết của từng doc
        docs_info = {}
        if vector_results['ids'] and vector_results['ids'][0]:
            for i, doc_id in enumerate(vector_results['ids'][0]):
                docs_info[doc_id] = {
                    'text': vector_results['documents'][0][i],
                    'metadata': vector_results['metadatas'][0][i] if vector_results['metadatas'] else {}
                }

        missing_ids = all_ids - set(docs_info.keys())
        if missing_ids:
            missing_docs = self.collection.get(ids=list(missing_ids), include=['documents', 'metadatas'])
            for i, doc_id in enumerate(missing_docs['ids']):
                docs_info[doc_id] = {
                    'text': missing_docs['documents'][i],
                    'metadata': missing_docs['metadatas'][i] if missing_docs['metadatas'] else {}
                }

        for doc_id in all_ids:
            vector_score = vector_scores.get(doc_id, 0.0)
            bm25_score = bm25_map.get(doc_id, 0.0)
            combined = self.alpha * vector_score + (1 - self.alpha) * bm25_score
            combined_scores.append({
                'id': doc_id,
                'text': docs_info[doc_id]['text'],
                'metadata': docs_info[doc_id]['metadata'],
                'score': combined,
                'vector_score': vector_score,
                'bm25_score': bm25_score
            })

        combined_scores.sort(key=lambda x: x['score'], reverse=True)
        return combined_scores[:top_k]