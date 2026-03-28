import sqlite3
import json
from pathlib import Path
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS files (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                path         TEXT NOT NULL UNIQUE,
                filename     TEXT NOT NULL,
                parent_dir   TEXT NOT NULL,
                extension    TEXT,
                size_bytes   INTEGER,
                status       TEXT NOT NULL DEFAULT 'pending',
                target_folder TEXT,
                llm_reason   TEXT,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_at DATETIME
            );

            CREATE TABLE IF NOT EXISTS folders (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                path         TEXT NOT NULL UNIQUE,
                parent_dir   TEXT NOT NULL,
                name         TEXT NOT NULL,
                sample_files TEXT,
                file_count   INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
            CREATE INDEX IF NOT EXISTS idx_files_parent ON files(parent_dir);
        """)


def upsert_file(path: str, filename: str, parent_dir: str, extension: str, size_bytes: int):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO files (path, filename, parent_dir, extension, size_bytes, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
            ON CONFLICT(path) DO NOTHING
        """, (path, filename, parent_dir, extension, size_bytes))


def upsert_folder(path: str, parent_dir: str, name: str, sample_files: list, file_count: int):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO folders (path, parent_dir, name, sample_files, file_count)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                sample_files = excluded.sample_files,
                file_count   = excluded.file_count
        """, (path, parent_dir, name, json.dumps(sample_files, ensure_ascii=False), file_count))


def get_files_by_status(status: str, parent_dir: str = None) -> list:
    with get_conn() as conn:
        if parent_dir:
            rows = conn.execute(
                "SELECT * FROM files WHERE status=? AND parent_dir=? ORDER BY filename",
                (status, parent_dir)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM files WHERE status=? ORDER BY parent_dir, filename",
                (status,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_folders_by_parent(parent_dir: str) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM folders WHERE parent_dir=? ORDER BY name",
            (parent_dir,)
        ).fetchall()
        return [dict(r) for r in rows]


def set_status(file_id: int, status: str, target_folder: str = None, reason: str = None):
    with get_conn() as conn:
        conn.execute("""
            UPDATE files SET
                status        = ?,
                target_folder = COALESCE(?, target_folder),
                llm_reason    = COALESCE(?, llm_reason),
                processed_at  = CASE WHEN ? IN ('done','failed') THEN CURRENT_TIMESTAMP ELSE processed_at END
            WHERE id = ?
        """, (status, target_folder, reason, status, file_id))


def set_excluded_by_ids(ids: list):
    with get_conn() as conn:
        conn.executemany(
            "UPDATE files SET status='excluded' WHERE id=?",
            [(i,) for i in ids]
        )


def set_pending_by_ids(ids: list):
    with get_conn() as conn:
        conn.executemany(
            "UPDATE files SET status='pending' WHERE id=?",
            [(i,) for i in ids]
        )


def get_stats() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt, SUM(size_bytes) as total_bytes FROM files GROUP BY status"
        ).fetchall()
        return {r["status"]: {"count": r["cnt"], "bytes": r["total_bytes"] or 0} for r in rows}


def get_all_files(parent_dir: str = None) -> list:
    with get_conn() as conn:
        if parent_dir:
            rows = conn.execute(
                "SELECT * FROM files WHERE parent_dir=? ORDER BY status, filename",
                (parent_dir,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM files ORDER BY parent_dir, status, filename"
            ).fetchall()
        return [dict(r) for r in rows]
