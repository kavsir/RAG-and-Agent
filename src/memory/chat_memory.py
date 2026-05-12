import json
import os


class ChatMemory:

    def __init__(self):

        self.path = "src/memory/chat_history.json"

        if os.path.exists(self.path):

            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.history = json.load(f)

            except:
                self.history = []
                self.save()

        else:

            self.history = []
            self.save()

    def add(self, user, ai):

        self.history.append({
            "user": user,
            "ai": ai
        })

        self.save()

    def get_history(self, k=5):
        
        return self.history[-k:]

    def save(self):

        os.makedirs("src/memory", exist_ok=True)

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)