"""
Hybrid Retriever: Kết hợp Dense Retrieval (ChromaDB + BAAI/bge-m3) và Sparse Retrieval (BM25)
sử dụng Reciprocal Rank Fusion (RRF) và Metadata Filtering.
"""
import pickle
import logging
from typing import List, Dict, Any, Optional

from src.config.settings import settings
from src.ingestion.vector_store import get_chroma_client, get_embedding_model
from src.rag.query_analyzer import AnalyzedQuery

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Retriever cho một collection cụ thể, kết hợp Dense Search và BM25."""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self.chroma_client = get_chroma_client()
        self.embedding_model = get_embedding_model()

        # Lấy Chroma collection
        try:
            self.collection = self.chroma_client.get_collection(collection_name)
        except Exception as e:
            logger.warning(f"Collection '{collection_name}' chua ton tai trong Chroma: {e}")
            self.collection = None

        # Load BM25 Index
        self.bm25_index = None
        self.bm25_corpus: List[str] = []
        self.bm25_doc_ids: List[str] = []
        self.bm25_metadatas: List[Dict[str, Any]] = []
        self._load_bm25()

    def _load_bm25(self):
        bm25_path = settings.CHROMA_PATH / f"bm25_{self.collection_name}.pkl"
        if bm25_path.exists():
            try:
                with open(bm25_path, "rb") as f:
                    data = pickle.load(f)
                    self.bm25_index = data.get("index")
                    self.bm25_corpus = data.get("corpus", [])
                    self.bm25_doc_ids = data.get("doc_ids", [])
                    self.bm25_metadatas = data.get("metadatas", [])
                logger.debug(f"Da tai BM25 index cho collection '{self.collection_name}' ({len(self.bm25_corpus)} docs)")
            except Exception as e:
                logger.error(f"Loi doc file BM25 {bm25_path}: {e}")
        else:
            logger.debug(f"Chua tim thay file BM25 tai: {bm25_path}")

    def dense_search(
        self, query: str, top_k: int = 15, where_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Tìm kiếm ngữ nghĩa qua Vector Embedding."""
        if not self.collection:
            return []

        try:
            emb = self.embedding_model.encode(query, normalize_embeddings=True).tolist()
            kwargs = {
                "query_embeddings": [emb],
                "n_results": min(top_k, max(1, self.collection.count())),
                "include": ["documents", "metadatas", "distances"],
            }
            if where_filter:
                kwargs["where"] = where_filter

            results = self.collection.query(**kwargs)
            docs = []
            if results and results.get("documents") and results["documents"][0]:
                for i in range(len(results["documents"][0])):
                    doc_id = results["ids"][0][i]
                    text = results["documents"][0][i]
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    # Cosine distance: similarity = 1 - distance
                    dist = results["distances"][0][i] if results.get("distances") else 0.5
                    score = max(0.0, 1.0 - dist)
                    docs.append({
                        "id": doc_id,
                        "text": text,
                        "metadata": meta,
                        "score": float(score),
                        "retrieval_method": "dense",
                    })
            return docs
        except Exception as e:
            logger.error(f"Loi dense search tren collection '{self.collection_name}': {e}")
            return []

    def bm25_search(
        self, query: str, top_k: int = 15, where_filter: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Tìm kiếm từ khóa qua BM25."""
        if not self.bm25_index or not self.bm25_corpus:
            return []

        try:
            tokens = query.lower().split()
            scores = self.bm25_index.get_scores(tokens)

            # Lấy danh sách index sắp xếp giảm dần theo điểm
            ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

            docs = []
            max_score = max(scores) if len(scores) > 0 and max(scores) > 0 else 1.0

            for idx in ranked_indices:
                if len(docs) >= top_k:
                    break
                raw_score = float(scores[idx])
                if raw_score <= 0.0:
                    continue

                meta = self.bm25_metadatas[idx] if idx < len(self.bm25_metadatas) else {}

                # Áp dụng where_filter nếu có
                if where_filter:
                    matched = True
                    for k, v in where_filter.items():
                        if meta.get(k) != v:
                            matched = False
                            break
                    if not matched:
                        continue

                norm_score = raw_score / max_score
                docs.append({
                    "id": self.bm25_doc_ids[idx] if idx < len(self.bm25_doc_ids) else f"bm25_{idx}",
                    "text": self.bm25_corpus[idx],
                    "metadata": meta,
                    "score": norm_score,
                    "retrieval_method": "bm25",
                })
            return docs
        except Exception as e:
            logger.error(f"Loi BM25 search tren collection '{self.collection_name}': {e}")
            return []

    def hybrid_search(
        self,
        query: str,
        top_k: int = 20,
        where_filter: Optional[Dict[str, Any]] = None,
        rrf_k: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Kết hợp Dense và BM25 bằng Reciprocal Rank Fusion (RRF).
        RRF_score = 1 / (rrf_k + rank_dense) + 1 / (rrf_k + rank_bm25)
        """
        dense_results = self.dense_search(query, top_k=top_k * 2, where_filter=where_filter)
        bm25_results = self.bm25_search(query, top_k=top_k * 2, where_filter=where_filter)

        # Nếu có filter nhưng không ra kết quả nào, chỉ fallback bỏ filter nếu KHÔNG PHẢI filter thực thể mạnh (course_code)
        has_strong_entity = bool(where_filter and "course_code" in where_filter)
        if where_filter and not dense_results and not bm25_results and not has_strong_entity:
            logger.info(f"Khong tim thay ket qua voi filter {where_filter}, thu lai khong co filter")
            dense_results = self.dense_search(query, top_k=top_k * 2, where_filter=None)
            bm25_results = self.bm25_search(query, top_k=top_k * 2, where_filter=None)

        rrf_scores: Dict[str, float] = {}
        doc_map: Dict[str, Dict[str, Any]] = {}
        methods: Dict[str, set] = {}

        # Xử lý rank từ Dense
        for rank, doc in enumerate(dense_results):
            doc_id = doc["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank + 1)
            doc_map[doc_id] = doc
            methods.setdefault(doc_id, set()).add("dense")

        # Xử lý rank từ BM25
        for rank, doc in enumerate(bm25_results):
            doc_id = doc["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank + 1)
            if doc_id not in doc_map:
                doc_map[doc_id] = doc
            methods.setdefault(doc_id, set()).add("bm25")

        # Sắp xếp theo điểm RRF
        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        merged = []
        for doc_id in sorted_ids[:top_k]:
            item = doc_map[doc_id]
            used_methods = methods.get(doc_id, set())
            method_label = "hybrid" if len(used_methods) > 1 else list(used_methods)[0]
            item["score"] = round(rrf_scores[doc_id], 4)
            item["retrieval_method"] = method_label
            merged.append(item)

        return merged


# Cache các instances HybridRetriever
_retriever_instances: Dict[str, HybridRetriever] = {}


def get_collection_retriever(collection_name: str) -> HybridRetriever:
    global _retriever_instances
    if collection_name not in _retriever_instances:
        _retriever_instances[collection_name] = HybridRetriever(collection_name)
    return _retriever_instances[collection_name]


def retrieve_candidates(analyzed_query: AnalyzedQuery, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Hàm truy xuất tài liệu ứng viên chính thức, điều hướng thông minh theo phân tích domain và metadata filter.
    """
    k = top_k or settings.RETRIEVAL_CANDIDATES
    query_str = analyzed_query.rewritten_query
    primary_domain = analyzed_query.domain
    where_filter = analyzed_query.to_filter_dict() or None

    logger.info(f"Retrieving candidates for domain='{primary_domain}', filter={where_filter}, query='{query_str}'")

    results = []
    # 1. Truy xuất từ collection mục tiêu
    primary_retriever = get_collection_retriever(primary_domain)
    results = primary_retriever.hybrid_search(query_str, top_k=k, where_filter=where_filter)

    # 2. Nếu kết quả ít hoặc không chắc chắn, chỉ mở rộng truy xuất sang các collection khác nếu KHÔNG CÓ course_code
    if len(results) < 3 and not analyzed_query.course_code:
        logger.info("Ket qua tu collection chinh it, mo rong tim kiem sang cac collection khac...")
        other_collections = [c for c in ["course_detail", "curriculum", "regulation"] if c != primary_domain]
        for col in other_collections:
            sec_retriever = get_collection_retriever(col)
            sec_docs = sec_retriever.hybrid_search(query_str, top_k=max(3, k // 2), where_filter=None)
            results.extend(sec_docs)

    # Loại bỏ trùng lặp id
    seen_ids = set()
    unique_results = []
    for r in results:
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            unique_results.append(r)

    unique_results.sort(key=lambda x: x["score"], reverse=True)
    logger.info(f"Tong so candidates tim thay: {len(unique_results[:k])}")
    return unique_results[:k]
