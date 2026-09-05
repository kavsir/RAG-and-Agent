"""
Student Profile Memory: Quản lý thông tin cá nhân của sinh viên trong runtime.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from src.config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = {
    "name": "Sinh viên CNTT",
    "major": "Công nghệ thông tin",
    "cohort": "K19",
    "style": "Thực hành",
    "email": "student@dainam.edu.vn",
}


class StudentMemory:
    def __init__(self, storage_path: Optional[Path] = None):
        self.path = storage_path or (settings.RUNTIME_DIR / "student_profile.json")
        self.profile = DEFAULT_PROFILE.copy()
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.profile.update(data)
            except Exception as e:
                logger.error(f"Loi doc file profile: {e}")
                self.save()
        else:
            self.save()

    def get_profile(self) -> Dict[str, Any]:
        return self.profile

    def update_profile(self, data: Dict[str, Any]):
        for k, v in data.items():
            if v is not None:
                self.profile[k] = v
        self.save()

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.profile, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Loi luu file profile: {e}")
