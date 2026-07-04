"""
Embeddings — Generate vector embeddings for company profiles and job descriptions.

Uses OpenAI's text-embedding-3-small model for high-quality embeddings.
Stores embeddings in FAISS for local use, with optional Pinecone sync.

Usage:
    python -m etl.embeddings --input data/raw/ --index data/embeddings/
"""

import argparse
import json
import os
import pickle
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ── In-Memory Vector Store (simple) ───────────────────────────


class InMemoryVectorStore:
    """Simple in-memory vector store for testing and small datasets."""

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions
        self._vectors: List[np.ndarray] = []
        self._metadata: List[Dict[str, Any]] = []
        self._ids: List[str] = []

    def add(self, vector: List[float], metadata: Dict[str, Any], id: str = "") -> None:
        """Add a single vector with metadata."""
        self._vectors.append(np.array(vector, dtype=np.float32))
        self._metadata.append(metadata)
        self._ids.append(id or str(len(self._ids)))

    def add_batch(
        self,
        vectors: List[List[float]],
        metadata_list: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ) -> None:
        """Add a batch of vectors."""
        for i, (vec, meta) in enumerate(zip(vectors, metadata_list)):
            id_val = ids[i] if ids and i < len(ids) else str(len(self._ids))
            self.add(vec, meta, id_val)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search for most similar vectors using cosine similarity."""
        if not self._vectors:
            return []

        query = np.array(query_vector, dtype=np.float32)
        query_norm = np.linalg.norm(query)
        if query_norm > 0:
            query = query / query_norm

        scores = []
        for i, vec in enumerate(self._vectors):
            vec_norm = np.linalg.norm(vec)
            if vec_norm > 0:
                vec = vec / vec_norm
            score = float(np.dot(query, vec))
            scores.append((i, score))

        scores.sort(key=lambda x: -x[1])
        results = []
        for idx, score in scores[:top_k]:
            results.append({
                "id": self._ids[idx],
                "score": score,
                **self._metadata[idx],
            })

        return results

    def save(self, path: str) -> None:
        """Save the vector store to disk."""
        os.makedirs(path, exist_ok=True)
        data = {
            "vectors": [v.tolist() for v in self._vectors],
            "metadata": self._metadata,
            "ids": self._ids,
            "dimensions": self.dimensions,
            "saved_at": datetime.now().isoformat(),
        }
        with open(os.path.join(path, "vectors.json"), "w") as fh:
            json.dump(data, fh, default=str)

    def load(self, path: str) -> bool:
        """Load the vector store from disk."""
        filepath = os.path.join(path, "vectors.json")
        if not os.path.exists(filepath):
            return False
        with open(filepath, "r") as fh:
            data = json.load(fh)
        self._vectors = [np.array(v, dtype=np.float32) for v in data.get("vectors", [])]
        self._metadata = data.get("metadata", [])
        self._ids = data.get("ids", [])
        self.dimensions = data.get("dimensions", self.dimensions)
        return True

    @property
    def size(self) -> int:
        return len(self._vectors)


# ── Config ─────────────────────────────────────────────────────

DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSIONS = 1536


def _get_api_key() -> str:
    """Get OpenAI API key from environment."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Set it in your environment or .env file."
        )
    return key


# ── Embedding Generator ───────────────────────────────────────


class EmbeddingGenerator:
    """Generate embeddings using OpenAI API."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=_get_api_key())
        return self._client

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        if not texts:
            return []

        # OpenAI allows batch embedding (up to 2048 texts per request)
        all_embeddings: List[List[float]] = []
        batch_size = 512

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions,
            )
            for item in response.data:
                all_embeddings.append(item.embedding)

        return all_embeddings

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        result = self.embed_texts([text])
        return result[0] if result else []

    def embed_lead(self, lead: Dict[str, Any]) -> List[float]:
        """Generate an embedding for a lead record by combining relevant fields."""
        text_parts = []
        for field in [
            "Company Name", "Job Title", "Industry", "Technology Stack",
            "Country", "City", "notes",
        ]:
            value = lead.get(field, "")
            if value:
                text_parts.append(str(value))

        combined = " | ".join(text_parts)
        return self.embed_text(combined)


# ── FAISS Vector Store ─────────────────────────────────────────


class FAISSVectorStore:
    """Local FAISS-based vector store for embeddings."""

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self.dimensions = dimensions
        self._index = None
        self._metadata: List[Dict[str, Any]] = []
        self._ids: List[str] = []

    def _ensure_faiss(self) -> None:
        try:
            import faiss
        except ImportError:
            raise RuntimeError("faiss-cpu not installed. Run: pip install faiss-cpu")

    def build_index(self, embeddings: List[List[float]], metadata: List[Dict[str, Any]]) -> None:
        """Build a FAISS index from embeddings and metadata."""
        self._ensure_faiss()
        import faiss

        vectors = np.array(embeddings, dtype=np.float32)
        n_vectors = len(vectors)

        # Normalize for cosine similarity
        faiss.normalize_L2(vectors)

        # Use IndexFlatIP for inner product (cosine similarity after normalization)
        if n_vectors < 1000:
            self._index = faiss.IndexFlatIP(self.dimensions)
        else:
            # Use IVF for larger datasets
            nlist = min(int(np.sqrt(n_vectors)), 256)
            quantizer = faiss.IndexFlatIP(self.dimensions)
            self._index = faiss.IndexIVFFlat(quantizer, self.dimensions, nlist)
            self._index.train(vectors)
            self._index.nprobe = min(nlist // 4, 32)

        self._index.add(vectors)
        self._metadata = metadata.copy()
        self._ids = [m.get("id", str(i)) for i, m in enumerate(metadata)]

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        if self._index is None or self._index.ntotal == 0:
            return []

        query = np.array([query_embedding], dtype=np.float32)
        import faiss
        faiss.normalize_L2(query)

        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(query, k)

        results: List[Dict[str, Any]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._metadata):
                continue
            results.append({
                "id": self._ids[idx],
                "score": float(score),
                **self._metadata[idx],
            })

        return results

    def save(self, path: str) -> None:
        """Save the index and metadata to disk."""
        self._ensure_faiss()
        import faiss

        os.makedirs(path, exist_ok=True)
        if self._index is not None:
            faiss.write_index(self._index, os.path.join(path, "index.faiss"))
        with open(os.path.join(path, "metadata.pkl"), "wb") as fh:
            pickle.dump({
                "metadata": self._metadata,
                "ids": self._ids,
                "dimensions": self.dimensions,
            }, fh)
        print(f"  Saved FAISS index to: {path}")

    def load(self, path: str) -> bool:
        """Load the index and metadata from disk."""
        index_file = os.path.join(path, "index.faiss")
        meta_file = os.path.join(path, "metadata.pkl")

        if not os.path.exists(index_file) or not os.path.exists(meta_file):
            return False

        self._ensure_faiss()
        import faiss

        self._index = faiss.read_index(index_file)
        with open(meta_file, "rb") as fh:
            data = pickle.load(fh)
        self._metadata = data.get("metadata", [])
        self._ids = data.get("ids", [])
        self.dimensions = data.get("dimensions", self.dimensions)
        print(f"  Loaded FAISS index: {len(self._ids)} vectors")
        return True


# ── Pinecone Vector Store (optional) ──────────────────────────


class PineconeVectorStore:
    """Pinecone cloud vector store (optional, requires API key)."""

    def __init__(
        self,
        index_name: str = "leadgen-embeddings",
        dimensions: int = DEFAULT_DIMENSIONS,
    ) -> None:
        self.index_name = index_name
        self.dimensions = dimensions
        self._index = None

    def _ensure_client(self) -> None:
        try:
            from pinecone import Pinecone
        except ImportError:
            raise RuntimeError("pinecone-client not installed. Run: pip install pinecone-client")

        api_key = os.environ.get("PINECONE_API_KEY", "")
        if not api_key:
            raise RuntimeError("PINECONE_API_KEY not set.")

        pc = Pinecone(api_key=api_key)
        existing = [idx.name for idx in pc.list_indexes()]
        if self.index_name not in existing:
            pc.create_index(
                name=self.index_name,
                dimension=self.dimensions,
                metric="cosine",
                spec={"serverless": {"cloud": "aws", "region": "us-east-1"}},
            )
        self._index = pc.Index(self.index_name)

    def upsert(self, vectors: List[Dict[str, Any]]) -> None:
        """Upsert vectors to Pinecone."""
        self._ensure_client()
        self._index.upsert(vectors=vectors)

    def query(
        self,
        vector: List[float],
        top_k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Query Pinecone for similar vectors."""
        self._ensure_client()
        kwargs: Dict[str, Any] = {"vector": vector, "top_k": top_k}
        if filter_dict:
            kwargs["filter"] = filter_dict
        results = self._index.query(**kwargs)
        return [
            {"id": m["id"], "score": m["score"], **m.get("metadata", {})}
            for m in results.get("matches", [])
        ]


# ── Public API ────────────────────────────────────────────────


def build_embeddings_index(
    leads: List[Dict[str, Any]],
    output_path: str = "data/embeddings",
    use_pinecone: bool = False,
) -> Any:
    """
    Build a vector index from a list of leads.
    Returns the vector store.
    """
    print(f"\n{'='*60}")
    print(f"  Building Embeddings Index")
    print(f"  Leads: {len(leads)} | Output: {output_path}")
    print(f"{'='*60}")

    if not leads:
        print("  No leads to embed.")
        return None

    # Generate embeddings
    print("  Generating embeddings...")
    generator = EmbeddingGenerator()

    texts = []
    metadata = []
    for i, lead in enumerate(leads):
        text_parts = []
        for field in ["Company Name", "Job Title", "Industry", "Technology Stack", "Country"]:
            val = lead.get(field, "")
            if val:
                text_parts.append(str(val))
        texts.append(" | ".join(text_parts))
        metadata.append({
            "id": f"lead_{i}",
            "company": lead.get("Company Name", ""),
            "title": lead.get("Job Title", ""),
            "industry": lead.get("Industry", ""),
            "country": lead.get("Country", ""),
        })

    embeddings = generator.embed_texts(texts)
    print(f"  Generated {len(embeddings)} embeddings (dim={len(embeddings[0]) if embeddings else 0})")

    if use_pinecone:
        store = PineconeVectorStore()
        vectors = [
            {"id": m["id"], "values": e, "metadata": m}
            for e, m in zip(embeddings, metadata)
        ]
        store.upsert(vectors)
        print("  Synced to Pinecone.")
        return store
    else:
        store = FAISSVectorStore()
        store.build_index(embeddings, metadata)
        store.save(output_path)
        return store


def search_similar_leads(
    query: str,
    top_k: int = 10,
    index_path: str = "data/embeddings",
) -> List[Dict[str, Any]]:
    """Search the embeddings index for leads similar to a query."""
    generator = EmbeddingGenerator()
    query_embedding = generator.embed_text(query)

    store = FAISSVectorStore()
    if not store.load(index_path):
        print("  No embeddings index found. Build one first.")
        return []

    return store.search(query_embedding, top_k=top_k)


# ── CLI ────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Embeddings Index")
    parser.add_argument("--input", "-i", help="Path to leads JSON or CSV")
    parser.add_argument("--output", "-o", default="data/embeddings", help="Index output path")
    parser.add_argument("--pinecone", action="store_true", help="Use Pinecone instead of FAISS")
    parser.add_argument("--search", "-s", help="Search query (instead of building index)")
    parser.add_argument("--top-k", "-k", type=int, default=10, help="Top K results for search")
    args = parser.parse_args()

    if args.search:
        results = search_similar_leads(args.search, args.top_k, args.output)
        for r in results:
            print(f"  [{r['score']:.3f}] {r.get('company', '?')} — {r.get('title', '?')}")
    elif args.input:
        import pandas as pd
        if args.input.endswith(".csv"):
            df = pd.read_csv(args.input)
            leads = df.to_dict(orient="records")
        else:
            with open(args.input, "r", encoding="utf-8") as fh:
                leads = json.load(fh)
        build_embeddings_index(leads, args.output, use_pinecone=args.pinecone)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
