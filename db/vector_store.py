"""
Vector Store — Thin re-export from etl.embeddings for backward compatibility.

All vector store implementations live in etl.embeddings.
This module simply re-exports them so existing imports still work:
    from db.vector_store import InMemoryVectorStore, FAISSVectorStore, get_vector_store
"""

from etl.embeddings import (
    FAISSVectorStore,
    InMemoryVectorStore,
)

# Re-export with the same API
__all__ = ["InMemoryVectorStore", "FAISSVectorStore", "get_vector_store"]


def get_vector_store(
    backend: str = "auto",
    dimensions: int = 1536,
):
    """
    Get a vector store instance.
    backend: "faiss", "memory", or "auto" (tries FAISS, falls back to memory)
    """
    if backend == "memory":
        return InMemoryVectorStore(dimensions)

    if backend == "faiss" or backend == "auto":
        try:
            import faiss  # noqa: F401
            return FAISSVectorStore(dimensions)
        except ImportError:
            if backend == "faiss":
                raise RuntimeError("faiss-cpu not installed.")
            print("  [INFO] FAISS not available. Using in-memory vector store.")
            return InMemoryVectorStore(dimensions)

    raise ValueError(f"Unknown vector store backend: {backend}")
