from src.memory.student_memory import StudentMemory
from src.memory.chat_memory import ChatMemory
from src.memory.vector_memory import VectorMemory

class MemoryManager:
    def __init__(self):
        self.profile = StudentMemory()
        self.chat = ChatMemory()
        self.vector = VectorMemory()

    def update(self, user_message, ai_message):
        # KHÔNG cập nhật profile từ chat nữa
        # self.profile.update_profile(user_message)
        self.chat.add(user_message, ai_message)
        self.vector.add_memory(user_message)