from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import os

from services.settings import load_env_files

load_env_files()

DB_PATH = Path(os.environ.get("FACADEGPT_DB", Path(__file__).with_name("facadegpt.db")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection(timeout: float = 30.0) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                display_name TEXT,
                seed_project_created INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                user_id TEXT REFERENCES users(id),
                name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS project_info (
                project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
                location TEXT,
                climate_zone TEXT,
                building_type TEXT DEFAULT '办公建筑',
                orientation TEXT,
                weight_lcce REAL DEFAULT 0.33,
                weight_lcc REAL DEFAULT 0.33,
                weight_sda REAL DEFAULT 0.34,
                weight_preset TEXT DEFAULT 'balanced',
                demand_text TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS parameter_ranges (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                param_name TEXT NOT NULL,
                param_type TEXT NOT NULL,
                min_val REAL,
                max_val REAL,
                options TEXT,
                fixed_val REAL,
                unit TEXT,
                step REAL,
                is_locked INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS schemes (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                scheme_name TEXT NOT NULL,
                scheme_label TEXT,
                strategy TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                risk_note TEXT,
                fitness_score REAL
            );

            CREATE TABLE IF NOT EXISTS scheme_params (
                scheme_id TEXT PRIMARY KEY REFERENCES schemes(id) ON DELETE CASCADE,
                horizontal_depth INTEGER,
                shading_type INTEGER,
                material INTEGER,
                spacing INTEGER,
                h_rotation INTEGER,
                v_rotation INTEGER,
                blade_depth INTEGER,
                window_distance INTEGER,
                wwr INTEGER,
                glass_type INTEGER
            );

            CREATE TABLE IF NOT EXISTS scheme_performance (
                scheme_id TEXT PRIMARY KEY REFERENCES schemes(id) ON DELETE CASCADE,
                lcce REAL,
                lcc REAL,
                sda REAL,
                lcce_rank TEXT,
                lcc_rank TEXT,
                sda_rank TEXT
            );

            CREATE TABLE IF NOT EXISTS teaching_feedback (
                scheme_id TEXT PRIMARY KEY REFERENCES schemes(id) ON DELETE CASCADE,
                key_conflict TEXT,
                priority TEXT,
                avoid TEXT,
                next_step TEXT,
                discussion TEXT
            );

            CREATE TABLE IF NOT EXISTS render_images (
                id TEXT PRIMARY KEY,
                scheme_id TEXT REFERENCES schemes(id) ON DELETE CASCADE,
                view_type TEXT,
                image_url TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS project_messages (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_labs (
                user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                params TEXT NOT NULL,
                performance TEXT,
                evaluations TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                page_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                page_start INTEGER,
                page_end INTEGER,
                text TEXT NOT NULL,
                embedding TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document
                ON knowledge_chunks(document_id, chunk_index);
            CREATE INDEX IF NOT EXISTS idx_project_messages_project
                ON project_messages(project_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_schemes_project
                ON schemes(project_id, created_at DESC);
            """
        )
        _ensure_columns(
            conn,
            "users",
            {
                "display_name": "TEXT",
                "seed_project_created": "INTEGER DEFAULT 0",
                "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
                "last_seen_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
            },
        )
        _ensure_columns(
            conn,
            "projects",
            {
                "user_id": "TEXT",
            },
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_projects_user_created
                ON projects(user_id, created_at DESC)
            """
        )
        _ensure_columns(
            conn,
            "render_images",
            {
                "source_type": "TEXT DEFAULT 'text_prompt'",
                "source_image_url": "TEXT",
                "status": "TEXT DEFAULT 'completed'",
                "provider": "TEXT",
                "prompt": "TEXT",
            },
        )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    if "options" in data and data["options"]:
        data["options"] = json.loads(data["options"])
    if "is_locked" in data:
        data["is_locked"] = bool(data["is_locked"])
    return data


def _ensure_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")
