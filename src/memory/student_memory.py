# src/memory/student_memory.py
import json
import os
from src.memory.profile_extractor import extract_profile  # chú ý đường dẫn

class StudentMemory:
    def __init__(self):
        self.path = "src/memory/student_profile.json"
        default_profile = {
            "name": None,
            "major": None,
            "cohort": None,
            "style": None,
            "email": None  # Thêm trường email
        }

        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.profile = json.load(f)
                # Đảm bảo các key mới có mặt (nếu file cũ chưa có)
                for key in default_profile:
                    if key not in self.profile:
                        self.profile[key] = default_profile[key]
            except:
                self.profile = default_profile
                self.save()
        else:
            self.profile = default_profile
            self.save()

    def update_profile(self, message):
        data = extract_profile(message)
        print(f"Extracted data: {data}")  # thêm dòng debug
        for k, v in data.items():
            if v:  # chỉ cập nhật nếu có giá trị
                self.profile[k] = v
        self.save()

    def get_profile(self):
        return self.profile

    def save(self):
        os.makedirs("src/memory", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.profile, f, ensure_ascii=False, indent=2)