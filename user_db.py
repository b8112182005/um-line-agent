import os
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Railway volume 掛載在 /data，本機開發用當前目錄
_data_dir = "/data" if os.path.isdir("/data") else "."
DB_PATH = os.path.join(_data_dir, "users.db")


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
                note TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        # 確保 note 欄位存在（舊 DB 升級）
        try:
            conn.execute("ALTER TABLE users ADD COLUMN note TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 欄位已存在
        conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                group_name TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
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

        # === 種子資料（確保每次啟動都在）===
        seed_users = [
            ("Ub9da80369a8d8c161d59c08cf282d783", "張紘瑀", "boss", "葉老闆/瑀墨塗料"),
            ("Ufbf785909fe2d05e8f0d2ee6784aa321", "悠悠", "approved", ""),
            ("U7a8bc939ffce3a958dbc8d3cabb7fcc0", "林逸婕", "approved", ""),
        ]
        for uid, name, role, note in seed_users:
            conn.execute(
                "INSERT OR IGNORE INTO users (line_user_id, display_name, role, note) VALUES (?, ?, ?, ?)",
                (uid, name, role, note),
            )

        seed_groups = [
            ("C5002a72a4fd12f95f97d27dce1858ea1", "瑀墨測試群", "allowed"),
        ]
        for gid, gname, status in seed_groups:
            conn.execute(
                "INSERT OR IGNORE INTO groups (group_id, group_name, status) VALUES (?, ?, ?)",
                (gid, gname, status),
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
            "SELECT line_user_id, display_name, note, created_at FROM users WHERE role = 'approved' ORDER BY created_at"
        ).fetchall()
    return [{"user_id": r[0], "display_name": r[1], "note": r[2] or "", "created_at": r[3]} for r in rows]


def list_pending() -> list[dict]:
    """列出所有待審核用戶"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT line_user_id, display_name, note, created_at FROM users WHERE role = 'pending' ORDER BY created_at"
        ).fetchall()
    return [{"user_id": r[0], "display_name": r[1], "note": r[2] or "", "created_at": r[3]} for r in rows]


def list_all_users() -> list[dict]:
    """列出所有用戶"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT line_user_id, display_name, role, note, created_at FROM users ORDER BY role, created_at"
        ).fetchall()
    return [{"user_id": r[0], "display_name": r[1], "role": r[2], "note": r[3] or "", "created_at": r[4]} for r in rows]


def set_note(user_id: str, note: str):
    """設定用戶備註"""
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET note = ? WHERE line_user_id = ?", (note, user_id)
        )
        conn.commit()


def remove_user(user_id: str) -> bool:
    """移除用戶（只能移除 approved/pending/blocked）"""
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM users WHERE line_user_id = ? AND role NOT IN ('boss', 'engineer')",
            (user_id,)
        )
        conn.commit()
    return cur.rowcount > 0


def find_user_by_name(name: str) -> list[dict]:
    """用暱稱模糊搜尋用戶"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT line_user_id, display_name, role, note FROM users WHERE display_name LIKE ? AND role NOT IN ('boss', 'engineer')",
            (f"%{name}%",)
        ).fetchall()
    return [{"user_id": r[0], "display_name": r[1], "role": r[2], "note": r[3] or ""} for r in rows]


# === 群組管理 ===

def get_group_status(group_id: str) -> str | None:
    """取得群組狀態"""
    with _conn() as conn:
        row = conn.execute(
            "SELECT status FROM groups WHERE group_id = ?", (group_id,)
        ).fetchone()
    return row[0] if row else None


def add_pending_group(group_id: str, group_name: str):
    """新增待審核群組"""
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO groups (group_id, group_name, status) VALUES (?, ?, 'pending')",
            (group_id, group_name),
        )
        conn.commit()


def get_latest_pending_group() -> dict | None:
    """取得最近一筆 pending 群組"""
    with _conn() as conn:
        row = conn.execute(
            "SELECT group_id, group_name FROM groups WHERE status = 'pending' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row:
        return {"group_id": row[0], "group_name": row[1]}
    return None


def approve_group(group_id: str):
    """允許群組"""
    with _conn() as conn:
        conn.execute(
            "UPDATE groups SET status = 'allowed' WHERE group_id = ?", (group_id,)
        )
        conn.commit()


def block_group(group_id: str):
    """封鎖群組"""
    with _conn() as conn:
        conn.execute(
            "UPDATE groups SET status = 'blocked' WHERE group_id = ?", (group_id,)
        )
        conn.commit()


def list_allowed_groups() -> list[dict]:
    """列出所有已允許的群組"""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT group_id, group_name, created_at FROM groups WHERE status = 'allowed' ORDER BY created_at"
        ).fetchall()
    return [{"group_id": r[0], "group_name": r[1], "created_at": r[2]} for r in rows]
