"""Offline PDF ingestion into the RAG vector store.

Sources are stored as "pdf:<filename>#p<page>" so citations can show the
page number without a schema migration.
"""

from __future__ import annotations

import io
import re

import numpy as np

from theoria.config import rag_db_path
from theoria.rag.retrieve import _embedder
from theoria.rag.store import VectorStore

CHUNK_CHARS = 800
MIN_CHUNK_CHARS = 60


def ingest_pdf(filename: str, content: bytes) -> dict:
    import fitz  # pymupdf — imported lazily so the CLI works without it

    doc = fitz.open(stream=io.BytesIO(content), filetype="pdf")
    embedder = _embedder()
    store = VectorStore(rag_db_path())

    safe_name = filename.rsplit("/", 1)[-1]
    page_count = doc.page_count
    added = 0
    try:
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text")
            for chunk in _chunk_page(text):
                emb = embedder.encode([chunk], normalize_embeddings=True)[0]
                store.add(f"pdf:{safe_name}#p{page_num}", chunk, np.asarray(emb))
                added += 1
    finally:
        store.close()
        doc.close()

    return {"filename": safe_name, "pages": page_count, "chunks": added}


def list_documents() -> list[dict]:
    db = rag_db_path()
    if not db.is_file():
        return []
    store = VectorStore(db)
    try:
        rows = store._conn.execute(
            "SELECT source, COUNT(*) FROM chunks WHERE source LIKE 'pdf:%' GROUP BY source"
        ).fetchall()
    finally:
        store.close()

    docs: dict[str, int] = {}
    for source, count in rows:
        name = source.split("#", 1)[0][len("pdf:"):]
        docs[name] = docs.get(name, 0) + count
    return [{"filename": name, "chunks": count} for name, count in sorted(docs.items())]


def _chunk_page(text: str) -> list[str]:
    """Split page text into ~CHUNK_CHARS pieces on paragraph boundaries,
    keeping display equations attached to their surrounding prose."""
    normalized = re.sub(r"[ \t]+", " ", text).strip()
    if not normalized:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[A-Z0-9])", normalized)]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if not para:
            continue
        if len(current) + len(para) + 1 > CHUNK_CHARS and current:
            chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n{para}" if current else para
    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]
