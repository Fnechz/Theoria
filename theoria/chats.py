"""Persistent chat storage — SQLite, fully offline, ChatGPT-style history.

One database at data/chats.db. Messages store the assistant's verification
metadata (SymPy / counterexample / Lean badges) as JSON so reopening an old
chat restores badges, not just text.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

from theoria.config import data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New chat',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    meta TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
"""


def _db_path() -> Path:
    return data_dir() / "chats.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def create_chat(title: str = "New chat") -> dict:
    now = time.time()
    chat_id = uuid.uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (chat_id, title, now, now),
        )
    return {"id": chat_id, "title": title, "created_at": now, "updated_at": now}


def list_chats() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_chat(chat_id: str) -> dict | None:
    with _connect() as conn:
        chat = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        if chat is None:
            return None
        messages = conn.execute(
            "SELECT role, content, meta, created_at FROM messages "
            "WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        ).fetchall()
    return {
        **dict(chat),
        "messages": [
            {
                "role": m["role"],
                "content": m["content"],
                "meta": json.loads(m["meta"]) if m["meta"] else None,
                "created_at": m["created_at"],
            }
            for m in messages
        ],
    }


def delete_chat(chat_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    return cur.rowcount > 0


def rename_chat(chat_id: str, title: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (title[:80], time.time(), chat_id),
        )


def append_message(chat_id: str, role: str, content: str, meta: dict | None = None) -> None:
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content, meta, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, role, content, json.dumps(meta) if meta else None, now),
        )
        conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
        # Auto-title from the first user message, ChatGPT-style.
        if role == "user":
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE chat_id = ? AND role = 'user'",
                (chat_id,),
            ).fetchone()
            if row["n"] == 1:
                title = content.strip().replace("\n", " ")
                if len(title) > 48:
                    title = title[:48].rsplit(" ", 1)[0] + "…"
                conn.execute(
                    "UPDATE chats SET title = ? WHERE id = ?", (title or "New chat", chat_id)
                )


def recent_history(chat_id: str, max_messages: int = 6, max_chars: int = 4000) -> list[dict]:
    """Last few turns for multi-turn context, oldest first, capped by size so
    the 4096-token context never overflows."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, max_messages),
        ).fetchall()
    history: list[dict] = []
    used = 0
    for row in rows:  # newest first; keep as many as fit
        content = row["content"]
        if used + len(content) > max_chars:
            break
        history.append({"role": row["role"], "content": content})
        used += len(content)
    history.reverse()
    return history
