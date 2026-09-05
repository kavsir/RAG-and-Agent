"""
Memory Subsystem: Quản lý bộ nhớ phiên có cấu trúc, hồ sơ sinh viên và lưu trữ SQLite cục bộ.
"""
from src.memory.session_models import SessionState, SessionMessage, SessionRecord
from src.memory.personal_models import PersonalFact, MemoryEvent, MemoryWriteResult
from src.memory.store import SessionStore, PersonalStore
from src.memory.sqlite_store import SQLiteSessionStore
from src.memory.session_memory import SessionMemoryService
from src.memory.personal_memory import PersonalMemoryService
from src.memory.authority_resolver import (
    resolve_academic_fact,
    resolve_personal_preference,
    resolve_conversation_entity,
)
from src.memory.memory_manager import MemoryManager, get_memory_manager

__all__ = [
    "SessionState",
    "SessionMessage",
    "SessionRecord",
    "PersonalFact",
    "MemoryEvent",
    "MemoryWriteResult",
    "SessionStore",
    "PersonalStore",
    "SQLiteSessionStore",
    "SessionMemoryService",
    "PersonalMemoryService",
    "resolve_academic_fact",
    "resolve_personal_preference",
    "resolve_conversation_entity",
    "MemoryManager",
    "get_memory_manager",
]
