"""Retrieve relevant chunks for a query."""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from theoria.config import rag_db_path
from theoria.rag.store import VectorStore

EMBED_MODEL = "BAAI/bge-small-en-v1.5"


@lru_cache(maxsize=1)
def _embedder() -> SentenceTransformer:
    return SentenceTransformer(EMBED_MODEL)


def retrieve(query: str, top_k: int = 3) -> list[dict]:
    db = rag_db_path()
    if not db.is_file():
        return []

    store = VectorStore(db)
    if store.count() == 0:
        store.close()
        return []

    model = _embedder()
    q_emb = model.encode([query], normalize_embeddings=True)[0]
    results = store.search(np.asarray(q_emb), top_k=top_k)
    store.close()
    return results
