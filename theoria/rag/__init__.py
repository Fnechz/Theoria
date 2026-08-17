"""RAG package."""

from theoria.rag.embed import build_index
from theoria.rag.retrieve import retrieve

__all__ = ["build_index", "retrieve"]
