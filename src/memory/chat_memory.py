"""
Chat History Memory: Lưu trữ lịch sử hội thoại trong runtime.
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

from src.config.settings import settings

logger = logging.getLogger(__name__)


class ChatMemory:
    def __init__(self, storage_path: Optional[Path] = None):
        self.path = storage_path or (settings.RUNTIME_DIR / "chat_history.json")
        self.history: List[Dict[str, str]] = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception as e:
                logger.error(f"Loi doc file chat history: {e}")
                self.history = []
        else:
            self.history = []

    def add(self, user_msg: str, ai_msg: str):
        self.history.append({
            "user": user_msg,
            "ai": ai_msg,
        })
        self.save()

    def get_history(self, k: int = 5) -> List[Dict[str, str]]:
        return self.history[-k:]

    def clear(self):
        self.history = []
        self.save()

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Loi luu file chat history: {e}")
