"""
SQLite Session Store: Hiện thực hóa SessionStore bằng cơ sở dữ liệu SQLite cục bộ.
Đảm bảo an toàn giao dịch, chế độ WAL, khóa ngoại, timeout, và cô lập triệt để theo conversation_id.
"""
import sqlite3
import json
import uuid
import logging
import datetime
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

from src.config.settings import settings
from src.memory.store import SessionStore, PersonalStore
from src.memory.session_models import SessionRecord, SessionMessage, SessionState
from src.memory.personal_models import PersonalFact, MemoryEvent

logger = logging.getLogger(__name__)


class SQLiteSessionStore(SessionStore, PersonalStore):
    """
    Kho lưu trữ phiên hội thoại và sự thật cá nhân dựa trên SQLite cục bộ (`runtime/advisor_memory.db`).
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (settings.RUNTIME_DIR / "advisor_memory.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Lấy hoặc tạo kết nối SQLite an toàn đa luồng được tái sử dụng trong cùng một thread."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=5.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        """Đóng kết nối thread-local nếu đang mở."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._local.conn = None

    def _init_db(self) -> None:
        """Khởi tạo bảng và chỉ mục nếu chưa tồn tại, kích hoạt WAL mode."""
        with self._get_connection() as conn:
            # Bật Write-Ahead Logging để tăng hiệu năng đọc/ghi đồng thời
            conn.execute("PRAGMA journal_mode = WAL;")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    conversation_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_activity_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata_json TEXT
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES sessions(conversation_id) ON DELETE CASCADE
                );
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conv_created
                ON session_messages(conversation_id, created_at);
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_states (
                    conversation_id TEXT PRIMARY KEY,
                    active_course_code TEXT,
                    active_course_name TEXT,
                    active_entity_type TEXT,
                    active_entities_json TEXT,
                    active_target TEXT,
                    last_source_ids_json TEXT,
                    unresolved_reference INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES sessions(conversation_id) ON DELETE CASCADE
                );
            """)

            # Đảm bảo bảng sessions có cột user_id
            cur = conn.execute("PRAGMA table_info(sessions);")
            cols = [row["name"] for row in cur.fetchall()]
            if "user_id" not in cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT 'local-user';")

            # Bảng lưu trữ sự thật cá nhân bền vững
            conn.execute("""
                CREATE TABLE IF NOT EXISTS personal_facts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    UNIQUE(user_id, fact_key)
                );
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_personal_facts_user_status
                ON personal_facts(user_id, status);
            """)

            # Bảng kiểm toán vòng đời biến động sự thật (Audit Events)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_events (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    old_value_json TEXT,
                    new_value_json TEXT,
                    source_type TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_events_user
                ON memory_events(user_id, created_at);
            """)

            conn.commit()
        logger.info(f"SQLiteSessionStore: Khoi tao CSDL thanh cong tai {self.db_path}")

    def create_session(
        self,
        conversation_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionRecord:
        """Tạo phiên hội thoại mới nếu chưa tồn tại."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_id = (metadata or {}).get("user_id", "local-user")
        meta_str = json.dumps(metadata, ensure_ascii=False) if metadata else None

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO sessions
                (conversation_id, user_id, created_at, updated_at, last_activity_at, status, metadata_json)
                VALUES (?, ?, ?, ?, ?, 'active', ?);
            """, (conversation_id, user_id, now_iso, now_iso, now_iso, meta_str))

            conn.execute("""
                INSERT OR IGNORE INTO session_states
                (conversation_id, active_course_code, active_course_name, active_entity_type,
                 active_entities_json, active_target, last_source_ids_json, unresolved_reference, updated_at)
                VALUES (?, NULL, NULL, NULL, '{}', NULL, '[]', 0, ?);
            """, (conversation_id, now_iso))
            conn.commit()

        session = self.get_session(conversation_id)
        if session is None:
            raise RuntimeError(f"Khong the tao phien hoi thoai {conversation_id}")
        return session

    def get_session(self, conversation_id: str) -> Optional[SessionRecord]:
        """Lấy thông tin phiên hội thoại."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM sessions WHERE conversation_id = ?;",
                (conversation_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return SessionRecord(
                conversation_id=row["conversation_id"],
                created_at=datetime.datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.datetime.fromisoformat(row["updated_at"]),
                last_activity_at=datetime.datetime.fromisoformat(row["last_activity_at"]),
                status=row["status"],
                metadata_json=row["metadata_json"],
            )

    def touch_session(self, conversation_id: str) -> None:
        """Cập nhật thời gian hoạt động gần nhất."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE sessions
                SET last_activity_at = ?, updated_at = ?
                WHERE conversation_id = ?;
            """, (now_iso, now_iso, conversation_id))
            conn.commit()

    def get_session_state(self, conversation_id: str) -> SessionState:
        """Lấy trạng thái thực thể của phiên; tự tạo mặc định nếu chưa có."""
        self.create_session(conversation_id)
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM session_states WHERE conversation_id = ?;",
                (conversation_id,),
            )
            row = cur.fetchone()
            if not row:
                return SessionState(conversation_id=conversation_id)

            active_entities = {}
            if row["active_entities_json"]:
                try:
                    active_entities = json.loads(row["active_entities_json"])
                except Exception:
                    active_entities = {}

            last_sources = []
            if row["last_source_ids_json"]:
                try:
                    last_sources = json.loads(row["last_source_ids_json"])
                except Exception:
                    last_sources = []

            return SessionState(
                conversation_id=row["conversation_id"],
                active_course_code=row["active_course_code"],
                active_course_name=row["active_course_name"],
                active_entity_type=row["active_entity_type"],
                active_entities=active_entities,
                active_target=row["active_target"],
                last_source_ids=last_sources,
                unresolved_reference=bool(row["unresolved_reference"]),
                updated_at=datetime.datetime.fromisoformat(row["updated_at"]),
            )

    def update_session_state(self, state: SessionState) -> None:
        """Cập nhật trạng thái thực thể có cấu trúc của phiên."""
        self.create_session(state.conversation_id)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        entities_json = json.dumps(state.active_entities, ensure_ascii=False)
        sources_json = json.dumps(state.last_source_ids, ensure_ascii=False)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO session_states
                (conversation_id, active_course_code, active_course_name, active_entity_type,
                 active_entities_json, active_target, last_source_ids_json, unresolved_reference, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    active_course_code = excluded.active_course_code,
                    active_course_name = excluded.active_course_name,
                    active_entity_type = excluded.active_entity_type,
                    active_entities_json = excluded.active_entities_json,
                    active_target = excluded.active_target,
                    last_source_ids_json = excluded.last_source_ids_json,
                    unresolved_reference = excluded.unresolved_reference,
                    updated_at = excluded.updated_at;
            """, (
                state.conversation_id,
                state.active_course_code,
                state.active_course_name,
                state.active_entity_type,
                entities_json,
                state.active_target,
                sources_json,
                1 if state.unresolved_reference else 0,
                now_iso,
            ))
            conn.execute("""
                UPDATE sessions
                SET updated_at = ?, last_activity_at = ?
                WHERE conversation_id = ?;
            """, (now_iso, now_iso, state.conversation_id))
            conn.commit()

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> SessionMessage:
        """Lưu thêm một tin nhắn vào lịch sử phiên."""
        self.create_session(conversation_id)
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_dt.isoformat()

        with self._get_connection() as conn:
            cur = conn.execute("""
                INSERT INTO session_messages
                (conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?);
            """, (conversation_id, role, content, now_iso))
            msg_id = cur.lastrowid
            conn.execute("""
                UPDATE sessions
                SET last_activity_at = ?, updated_at = ?
                WHERE conversation_id = ?;
            """, (now_iso, now_iso, conversation_id))
            conn.commit()

        return SessionMessage(
            id=msg_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=now_dt,
        )

    def get_recent_messages(
        self,
        conversation_id: str,
        k: int = 5,
    ) -> List[SessionMessage]:
        """Lấy k tin nhắn gần nhất theo thứ tự thời gian tăng dần."""
        with self._get_connection() as conn:
            cur = conn.execute("""
                SELECT id, conversation_id, role, content, created_at
                FROM session_messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?;
            """, (conversation_id, k))
            rows = cur.fetchall()

        # Đảo ngược lại để có thứ tự thời gian tăng dần (cũ nhất -> mới nhất)
        rows.reverse()
        messages = [
            SessionMessage(
                id=r["id"],
                conversation_id=r["conversation_id"],
                role=r["role"],
                content=r["content"],
                created_at=datetime.datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]
        return messages

    def clear_session(self, conversation_id: str) -> bool:
        """Xóa toàn bộ tin nhắn và reset trạng thái thực thể của phiên."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM session_messages WHERE conversation_id = ?;",
                (conversation_id,),
            )
            conn.execute("""
                UPDATE session_states
                SET active_course_code = NULL,
                    active_course_name = NULL,
                    active_entity_type = NULL,
                    active_entities_json = '{}',
                    active_target = NULL,
                    last_source_ids_json = '[]',
                    unresolved_reference = 0,
                    updated_at = ?
                WHERE conversation_id = ?;
            """, (now_iso, conversation_id))
            conn.execute("""
                UPDATE sessions
                SET updated_at = ?, last_activity_at = ?
                WHERE conversation_id = ?;
            """, (now_iso, now_iso, conversation_id))
            conn.commit()
        return True

    def delete_session(self, conversation_id: str) -> bool:
        """Xóa hoàn toàn phiên khỏi CSDL (cascade xóa messages và state)."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM sessions WHERE conversation_id = ?;",
                (conversation_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    # =========================================================================
    # PERSONAL STORE IMPLEMENTATION
    # =========================================================================
    def upsert_personal_fact(
        self,
        user_id: str,
        fact_key: str,
        value: Any,
        source_type: str,
        confidence: float = 1.0,
    ) -> PersonalFact:
        """Thêm mới hoặc cập nhật sự thật cá nhân của người dùng."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_dt.isoformat()
        val_str = json.dumps(value, ensure_ascii=False)

        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT id, created_at FROM personal_facts WHERE user_id = ? AND fact_key = ?;",
                (user_id, fact_key),
            )
            row = cur.fetchone()
            if row:
                fact_id = row["id"]
                created_iso = row["created_at"]
                conn.execute("""
                    UPDATE personal_facts
                    SET value_json = ?,
                        source_type = ?,
                        confidence = ?,
                        updated_at = ?,
                        status = 'ACTIVE'
                    WHERE id = ?;
                """, (val_str, source_type, confidence, now_iso, fact_id))
            else:
                fact_id = str(uuid.uuid4())
                created_iso = now_iso
                conn.execute("""
                    INSERT INTO personal_facts (
                        id, user_id, fact_key, value_json, source_type, confidence, created_at, updated_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE');
                """, (fact_id, user_id, fact_key, val_str, source_type, confidence, now_iso, now_iso))
            conn.commit()

        return PersonalFact(
            id=fact_id,
            user_id=user_id,
            fact_key=fact_key,
            value=value,
            source_type=source_type,
            confidence=confidence,
            created_at=datetime.datetime.fromisoformat(created_iso),
            updated_at=now_dt,
            status="ACTIVE",
        )

    def get_personal_fact(self, user_id: str, fact_key: str) -> Optional[PersonalFact]:
        """Lấy một sự thật cá nhân đang hoạt động (ACTIVE) theo khóa."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM personal_facts WHERE user_id = ? AND fact_key = ? AND status = 'ACTIVE';",
                (user_id, fact_key),
            )
            row = cur.fetchone()
            if not row:
                return None
            return PersonalFact(
                id=row["id"],
                user_id=row["user_id"],
                fact_key=row["fact_key"],
                value=json.loads(row["value_json"]),
                source_type=row["source_type"],
                confidence=float(row["confidence"]),
                created_at=datetime.datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.datetime.fromisoformat(row["updated_at"]),
                status=row["status"],
            )

    def get_all_personal_facts(self, user_id: str, status: str = "ACTIVE") -> List[PersonalFact]:
        """Lấy tất cả các sự thật cá nhân của người dùng."""
        with self._get_connection() as conn:
            if status == "ALL":
                cur = conn.execute(
                    "SELECT * FROM personal_facts WHERE user_id = ? ORDER BY fact_key ASC;",
                    (user_id,),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM personal_facts WHERE user_id = ? AND status = ? ORDER BY fact_key ASC;",
                    (user_id, status),
                )
            rows = cur.fetchall()
            facts = []
            for row in rows:
                facts.append(
                    PersonalFact(
                        id=row["id"],
                        user_id=row["user_id"],
                        fact_key=row["fact_key"],
                        value=json.loads(row["value_json"]),
                        source_type=row["source_type"],
                        confidence=float(row["confidence"]),
                        created_at=datetime.datetime.fromisoformat(row["created_at"]),
                        updated_at=datetime.datetime.fromisoformat(row["updated_at"]),
                        status=row["status"],
                    )
                )
            return facts

    def delete_personal_fact(self, user_id: str, fact_key: str) -> bool:
        """Xóa một sự thật cá nhân cụ thể của người dùng."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM personal_facts WHERE user_id = ? AND fact_key = ?;",
                (user_id, fact_key),
            )
            conn.commit()
            return cur.rowcount > 0

    def clear_personal_facts(self, user_id: str) -> int:
        """Xóa toàn bộ sự thật cá nhân của người dùng."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "DELETE FROM personal_facts WHERE user_id = ?;",
                (user_id,),
            )
            conn.commit()
            return cur.rowcount

    def log_memory_event(
        self,
        user_id: str,
        event_type: str,
        fact_key: str,
        old_value: Optional[Any],
        new_value: Optional[Any],
        source_type: str,
    ) -> MemoryEvent:
        """Ghi nhận nhật ký kiểm toán biến động bộ nhớ."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_iso = now_dt.isoformat()
        evt_id = str(uuid.uuid4())
        old_str = json.dumps(old_value, ensure_ascii=False) if old_value is not None else None
        new_str = json.dumps(new_value, ensure_ascii=False) if new_value is not None else None

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO memory_events (
                    id, user_id, event_type, fact_key, old_value_json, new_value_json, source_type, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (evt_id, user_id, event_type, fact_key, old_str, new_str, source_type, now_iso))
            conn.commit()

        return MemoryEvent(
            id=evt_id,
            user_id=user_id,
            event_type=event_type,
            fact_key=fact_key,
            old_value=old_value,
            new_value=new_value,
            source_type=source_type,
            created_at=now_dt,
        )

    def get_memory_events(self, user_id: str, limit: int = 50) -> List[MemoryEvent]:
        """Lấy danh sách nhật ký kiểm toán bộ nhớ."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM memory_events WHERE user_id = ? ORDER BY created_at DESC LIMIT ?;",
                (user_id, limit),
            )
            rows = cur.fetchall()
            events = []
            for row in rows:
                events.append(
                    MemoryEvent(
                        id=row["id"],
                        user_id=row["user_id"],
                        event_type=row["event_type"],
                        fact_key=row["fact_key"],
                        old_value=json.loads(row["old_value_json"]) if row["old_value_json"] else None,
                        new_value=json.loads(row["new_value_json"]) if row["new_value_json"] else None,
                        source_type=row["source_type"],
                        created_at=datetime.datetime.fromisoformat(row["created_at"]),
                    )
                )
            return events

