"""
Memory Manager: Điều phối Student Profile, Chat History và Vector Memory.
"""
from src.memory.student_memory import StudentMemory
from src.memory.chat_memory import ChatMemory
from src.memory.vector_memory import VectorMemory


class MemoryManager:
    def __init__(self):
        self.profile = StudentMemory()
        self.chat = ChatMemory()
        self.vector = VectorMemory()

    def update(self, user_message: str, ai_message: str):
        self.chat.add(user_message, ai_message)
        # Chi luu vector memory neu noi dung du dai
        if len(user_message) > 15:
            self.vector.add_memory(user_message)

    def get_conversation_history(self, k: int = 5) -> str:
        history = self.chat.get_history(k)
        return "\n".join(f"User: {h['user']}\nAI: {h['ai']}" for h in history)

    def clear(self):
        self.chat.clear()


_memory_manager_singleton = None


def get_memory_manager() -> MemoryManager:
    global _memory_manager_singleton
    if _memory_manager_singleton is None:
        _memory_manager_singleton = MemoryManager()
    return _memory_manager_singleton
