"""Build RAG index from curated math snippets and GSM8K samples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from theoria.config import data_dir, rag_db_path
from theoria.rag.store import VectorStore

EMBED_MODEL = "BAAI/bge-small-en-v1.5"


def load_chunks(data_root: Path) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []

    snippets = data_root / "math_snippets.json"
    if snippets.is_file():
        items = json.loads(snippets.read_text(encoding="utf-8"))
        for item in items:
            chunks.append((item.get("source", "math_snippets"), item["text"]))

    gsm8k = data_root / "gsm8k_sample.json"
    if gsm8k.is_file():
        items = json.loads(gsm8k.read_text(encoding="utf-8"))
        for item in items:
            text = f"Q: {item['question']}\nA: {item['answer']}"
            chunks.append(("gsm8k", text))

    return chunks


def build_index(data_root: Path | None = None, db_path: Path | None = None) -> int:
    root = data_root or data_dir()
    db = db_path or rag_db_path()
    chunks = load_chunks(root)
    if not chunks:
        raise RuntimeError(f"No chunks found under {root}")

    model = SentenceTransformer(EMBED_MODEL)
    store = VectorStore(db)

    texts = [text for _, text in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)

    for (source, text), emb in zip(chunks, embeddings, strict=True):
        store.add(source, text, np.asarray(emb))

    count = store.count()
    store.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Theoria RAG index")
    parser.add_argument("--data", type=Path, default=data_dir())
    parser.add_argument("--db", type=Path, default=rag_db_path())
    args = parser.parse_args()
    n = build_index(args.data, args.db)
    print(f"Indexed {n} chunks into {args.db}")


if __name__ == "__main__":
    main()
