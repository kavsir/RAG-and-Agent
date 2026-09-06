"""
SQLite Goal Store for Agent Core V1.1.
Ensures persistent storage of active and completed goals scoped strictly by:
- principal/user_id
- conversation_id
- goal_id
Survives system restart and enforces zero cross-session or cross-principal leakage.
"""
import sqlite3
import datetime
import threading
from pathlib import Path
from typing import Optional

from src.config.settings import settings
from src.agent_core.schemas import AgentGoalState, AgentStatus


class AgentGoalStore:
    """Kho lưu trữ trạng thái mục tiêu bền vững dựa trên SQLite."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else (settings.RUNTIME_DIR / "agent_goals.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            self._local.conn = conn
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_goals (
                    user_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    goal_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, conversation_id, goal_id)
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_goals_lookup
                ON agent_goals(user_id, conversation_id, status);
            """)

    def save_goal(self, user_id: str, conversation_id: str, state: AgentGoalState) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        state_json = state.model_dump_json()
        conn = self._get_connection()
        with conn:
            conn.execute("""
                INSERT INTO agent_goals (user_id, conversation_id, goal_id, status, state_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, conversation_id, goal_id) DO UPDATE SET
                    status = excluded.status,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
            """, (user_id, conversation_id, state.goal_id, state.status.value, state_json, now, now))

    def get_active_goal(
        self, user_id: str, conversation_id: str, goal_id: Optional[str] = None
    ) -> Optional[AgentGoalState]:
        """
        Lấy mục tiêu đang chờ người dùng phản hồi (status = NEEDS_USER_INPUT)
        được cô lập chặt chẽ theo user_id và conversation_id.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        if goal_id:
            cursor.execute("""
                SELECT state_json FROM agent_goals
                WHERE user_id = ? AND conversation_id = ? AND goal_id = ? AND status = ?
            """, (user_id, conversation_id, goal_id, AgentStatus.NEEDS_USER_INPUT.value))
        else:
            cursor.execute("""
                SELECT state_json FROM agent_goals
                WHERE user_id = ? AND conversation_id = ? AND status = ?
                ORDER BY updated_at DESC LIMIT 1
            """, (user_id, conversation_id, AgentStatus.NEEDS_USER_INPUT.value))

        row = cursor.fetchone()
        if not row:
            return None
        try:
            return AgentGoalState.model_validate_json(row[0])
        except Exception:
            return None

    def get_goal(self, user_id: str, conversation_id: str, goal_id: str) -> Optional[AgentGoalState]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT state_json FROM agent_goals
            WHERE user_id = ? AND conversation_id = ? AND goal_id = ?
        """, (user_id, conversation_id, goal_id))
        row = cursor.fetchone()
        if not row:
            return None
        return AgentGoalState.model_validate_json(row[0])

    def clear_all(self):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM agent_goals;")


_goal_store_instance: Optional[AgentGoalStore] = None


def get_agent_goal_store() -> AgentGoalStore:
    global _goal_store_instance
    if _goal_store_instance is None:
        _goal_store_instance = AgentGoalStore()
    return _goal_store_instance
