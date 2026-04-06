import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "users.db"


def _conn():
    return sqlite3.connect(DB_PATH)


def init_db(boss_user_id: str, engineer_user_id: str = ""):
    """建表 + 確保工程師與老闆 ID 存在"""
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                line_user_id TEXT PRIMARY KEY,
                display_name TEXT DEFAULT '',
                role TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        # 工程師（最高權限）
        if engineer_user_id:
            conn.execute(
                "INSERT OR IGNORE INTO users (line_user_id, display_name, role) VALUES (?, ?, ?)",
                (engineer_user_id, "工程師", "engineer"),
            )
            # 若已存在但角色不對，更新
            conn.execute(
                "UPDATE users SET role = 'engineer' WHERE line_user_id = ? AND role != 'engineer'",
                (engineer_user_id,),
            )
        # 老闆
        if boss_user_id and boss_user_id != engineer_user_id:
            conn.execute(
                "INSERT OR IGNORE INTO users (line_user_id, display_name, role) VALUES (?, ?, ?)",
                (boss_user_id, "老闆", "boss"),
            )
        conn.commit()
    logger.info("users DB 初始化完成")


def get_role(user_id: str) -> str | None:
    """取得用戶角色，不存在回傳 None"""
    with _conn() as conn:
        row = conn.execute(
            "SELECT role FROM users WHERE line_user_id = ?", (user_id,)
        ).fetchone()
    return row[0] if row else None


def add_pending(user_id: str, display_name: str):
    """新增待審核用戶"""
    with _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (line_user_id, display_name, role) VALUES (?, ?, 'pending')",
            (user_id, display_name),
        )
        conn.commit()


def get_latest_pending() -> dict | None:
    """取得最近一筆 pending 用戶"""
    with _conn() as conn:
        row = conn.execute(
            "SELECT line_user_id, display_name FROM users WHERE role = 'pending' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row:
        return {"user_id": row[0], "display_name": row[1]}
    return None


def approve_user(user_id: str):
    """審核通過"""
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET role = 'approved' WHERE line_user_id = ?", (user_id,)
        )
        conn.commit()


def block_user(user_id: str):
    """拒絕"""
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET role = 'blocked' WHERE line_user_id = ?", (user_id,)
        )
        conn.commit()


def list_approved() -> list[dict]:
    """列出所有已通過的用戶"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT line_user_id, display_name, created_at FROM users WHERE role = 'approved' ORDER BY created_at"
        ).fetchall()
    return [{"user_id": r[0], "display_name": r[1], "created_at": r[2]} for r in rows]


def list_pending() -> list[dict]:
    """列出所有待審核用戶"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT line_user_id, display_name, created_at FROM users WHERE role = 'pending' ORDER BY created_at"
        ).fetchall()
    return [{"user_id": r[0], "display_name": r[1], "created_at": r[2]} for r in rows]
