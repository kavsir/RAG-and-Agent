"""
Exact Cache: Bộ nhớ đệm câu hỏi và câu trả lời chính xác trong runtime.
"""
from typing import Optional, Dict, Any, List


class ExactCache:
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        norm_key = key.strip().lower()
        return self.cache.get(norm_key)

    def set(
        self,
        key: str,
        answer: str,
        category: str = "DOMAIN_DATA",
        sources: Optional[List[Any]] = None,
        tool_intent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        norm_key = key.strip().lower()
        self.cache[norm_key] = {
            "answer": answer,
            "category": category,
            "tool_intent": tool_intent,
            "sources": sources or [],
            "metadata": metadata or {},
        }

    def clear(self):
        self.cache.clear()

    def size(self) -> int:
        return len(self.cache)


_cache_singleton = ExactCache()


def get_exact_cache() -> ExactCache:
    return _cache_singleton
