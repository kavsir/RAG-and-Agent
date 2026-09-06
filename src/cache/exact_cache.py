"""
Exact Cache: Bộ nhớ đệm câu hỏi và câu trả lời chính xác trong runtime.
Hỗ trợ cả khóa chuẩn tắc ngữ cảnh an toàn (Context-Safe Cache Key) và API truyền thống.
"""
import re
import unicodedata
from typing import Optional, Dict, Any, List


class ExactCache:
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}

    def _make_key(self, key: str, profile_fingerprint: Optional[str] = None) -> str:
        norm = unicodedata.normalize("NFC", key.strip().lower())
        norm = re.sub(r"\s+", " ", norm)
        if profile_fingerprint:
            return f"{norm}::profile:{profile_fingerprint.strip()}"
        return norm

    def get(self, key: str, profile_fingerprint: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if "::" in key and profile_fingerprint is None:
            entry = self.cache.get(key)
            if entry is not None:
                return entry

        norm_key = self._make_key(key, profile_fingerprint)
        return self.cache.get(norm_key)

    def set(
        self,
        key: str,
        answer: str,
        category: str = "DOMAIN_DATA",
        sources: Optional[List[Any]] = None,
        tool_intent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        profile_fingerprint: Optional[str] = None,
    ):
        if "::" in key and profile_fingerprint is None:
            cache_key = key
        else:
            cache_key = self._make_key(key, profile_fingerprint)

        self.cache[cache_key] = {
            "answer": answer,
            "category": category,
            "tool_intent": tool_intent,
            "sources": sources or [],
            "metadata": metadata or {},
            "profile_fingerprint": profile_fingerprint,
        }

    def delete(self, key: str, profile_fingerprint: Optional[str] = None) -> bool:
        if key in self.cache:
            del self.cache[key]
            return True
        norm_key = self._make_key(key, profile_fingerprint)
        if norm_key in self.cache:
            del self.cache[norm_key]
            return True
        return False

    def clear(self):
        self.cache.clear()

    def size(self) -> int:
        return len(self.cache)


_cache_singleton = ExactCache()


def get_exact_cache() -> ExactCache:
    return _cache_singleton
