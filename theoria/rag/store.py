"""SQLite-backed vector store with numpy cosine fallback."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np


class VectorStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL
            )
            """
        )
        self._conn.commit()

    def add(self, source: str, content: str, embedding: np.ndarray) -> None:
        blob = embedding.astype(np.float32).tobytes()
        self._conn.execute(
            "INSERT INTO chunks (source, content, embedding) VALUES (?, ?, ?)",
            (source, content, blob),
        )
        self._conn.commit()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
        return int(row[0]) if row else 0

    def search(self, query_embedding: np.ndarray, top_k: int = 3) -> list[dict]:
        rows = self._conn.execute(
            "SELECT source, content, embedding FROM chunks"
        ).fetchall()
        if not rows:
            return []

        q = query_embedding.astype(np.float32)
        q_norm = np.linalg.norm(q) + 1e-8
        scored: list[tuple[float, str, str]] = []

        for source, content, blob in rows:
            vec = np.frombuffer(blob, dtype=np.float32)
            denom = (np.linalg.norm(vec) * q_norm) + 1e-8
            score = float(np.dot(vec, q) / denom)
            scored.append((score, source, content))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"source": source, "content": content, "score": score}
            for score, source, content in scored[:top_k]
        ]

    def close(self) -> None:
        self._conn.close()

    def export_meta(self) -> str:
        return json.dumps({"chunks": self.count(), "path": str(self.db_path)})
