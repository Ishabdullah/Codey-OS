#!/usr/bin/env python3
"""
Multilingual Embeddings for Codey-V3 hierarchical memory.

Uses sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2:
- 384-dim vectors, supports 50+ languages
- Same concept described in English, Arabic, or Spanish maps to the same vector
- Lazy-loads model on first use to avoid overhead when embeddings aren't needed

On Termux/Android: falls back to nomic-embed-text-v1.5 via llama-server
(port 8082) if sentence-transformers is unavailable.
"""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.logger import error, info, success

# Multilingual embedding model — paraphrase-multilingual-MiniLM-L12-v2
# 384-dim, 50+ languages, same vector space for all languages
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


@dataclass
class Embedding:
    id: int
    file_path: str
    chunk_start: int
    chunk_end: int
    embedding: bytes
    created_at: int


class EmbeddingModel:
    """
    Manages multilingual embedding model.

    Primary: sentence-transformers paraphrase-multilingual-MiniLM-L12-v2
    Fallback: nomic-embed-text-v1.5 via llama-server (port 8082)

    Both produce vectors in a language-agnostic space — the same concept
    described in different languages maps to the same vector region.
    """

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self.model_name = model_name
        self._model = None
        self._loaded = False
        self._backend = None  # "sentence-transformers" or "llama-server"

    def _load_model(self):
        if self._loaded:
            return

        # Try sentence-transformers first (multilingual model)
        try:
            from sentence_transformers import SentenceTransformer

            info(f"Loading multilingual embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            self._loaded = True
            self._backend = "sentence-transformers"
            success(f"Multilingual embedding model loaded ({EMBEDDING_DIM}d, 50+ languages)")
            return
        except ImportError:
            info("sentence-transformers not available, trying llama-server fallback")
        except Exception as e:
            info(f"sentence-transformers failed: {e}, trying llama-server fallback")

        # Fallback: nomic-embed-text via llama-server (port 8082)
        try:
            import urllib.request
            import json

            url = "http://127.0.0.1:8082/health"
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    self._loaded = True
                    self._backend = "llama-server"
                    success("Using nomic-embed-text-v1.5 fallback (llama-server:8082)")
                    return
        except Exception:
            pass

        error("No embedding backend available")
        self._loaded = False

    def embed(self, text: str) -> Optional[bytes]:
        """Generate embedding for text (language-agnostic)."""
        self._load_model()
        if not self._loaded:
            return None

        try:
            import numpy as np

            if self._backend == "sentence-transformers":
                embedding = self._model.encode(text, convert_to_numpy=True)
                return embedding.astype(np.float32).tobytes()
            elif self._backend == "llama-server":
                return self._embed_via_server(text)
        except Exception as e:
            error(f"Embedding error: {e}")
            return None

    def embed_batch(self, texts: List[str]) -> Optional[List[bytes]]:
        """Generate embeddings for multiple texts."""
        self._load_model()
        if not self._loaded:
            return None

        try:
            import numpy as np

            if self._backend == "sentence-transformers":
                embeddings = self._model.encode(texts, convert_to_numpy=True)
                return [e.astype(np.float32).tobytes() for e in embeddings]
            elif self._backend == "llama-server":
                return [self._embed_via_server(t) for t in texts]
        except Exception as e:
            error(f"Batch embedding error: {e}")
            return None

    def _embed_via_server(self, text: str) -> Optional[bytes]:
        """Embed text via llama-server /v1/embeddings endpoint."""
        try:
            import json
            import urllib.request
            import numpy as np

            payload = json.dumps({
                "input": text,
                "model": "nomic-embed-text-v1.5",
            }).encode()

            req = urllib.request.Request(
                "http://127.0.0.1:8082/v1/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                vec = data["data"][0]["embedding"]
                return np.array(vec, dtype=np.float32).tobytes()
        except Exception as e:
            error(f"llama-server embedding failed: {e}")
            return None

    def is_loaded(self) -> bool:
        return self._loaded

    def get_backend(self) -> str:
        return self._backend or "none"


class EmbeddingStore:
    """
    SQLite-backed storage for multilingual embeddings.

    Stores vectors in a language-agnostic space — the same concept in
    different languages produces vectors that are close in cosine space.
    """

    def __init__(self, db_path: Path = None):
        if db_path is None:
            db_dir = Path.home() / ".codey-v3"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "state.db"
        self.db_path = db_path
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS longterm_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    chunk_start INTEGER NOT NULL,
                    chunk_end INTEGER NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_path 
                ON longterm_embeddings(file_path)
            """)
            conn.commit()
        finally:
            conn.close()

    def store(self, file_path: str, chunk_start: int, chunk_end: int, embedding: bytes) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO longterm_embeddings 
                (file_path, chunk_start, chunk_end, embedding, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (file_path, chunk_start, chunk_end, embedding, int(time.time())),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def store_batch(self, embeddings: List[Tuple[str, int, int, bytes]]) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT INTO longterm_embeddings 
                (file_path, chunk_start, chunk_end, embedding, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                embeddings,
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def search(self, query_embedding: bytes, limit: int = 5) -> List[Dict]:
        try:
            import numpy as np

            query_vec = np.frombuffer(query_embedding, dtype=np.float32)
            query_norm = np.linalg.norm(query_vec)
            if query_norm == 0:
                return []
        except Exception as e:
            error(f"Failed to load query embedding: {e}")
            return []

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, file_path, chunk_start, chunk_end, embedding, created_at
                FROM longterm_embeddings
            """)

            scored = []
            for row in cursor.fetchall():
                try:
                    import numpy as np

                    vec = np.frombuffer(row["embedding"], dtype=np.float32)
                    vec_norm = np.linalg.norm(vec)
                    if vec_norm == 0:
                        continue
                    score = float(np.dot(query_vec, vec) / (query_norm * vec_norm))
                    scored.append(
                        (
                            score,
                            {
                                "id": row["id"],
                                "file_path": row["file_path"],
                                "chunk_start": row["chunk_start"],
                                "chunk_end": row["chunk_end"],
                                "created_at": row["created_at"],
                                "similarity": round(score, 4),
                            },
                        )
                    )
                except Exception:
                    continue

            scored.sort(key=lambda x: x[0], reverse=True)
            return [item for _, item in scored[:limit]]

        finally:
            conn.close()

    def delete_by_file(self, file_path: str) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM longterm_embeddings WHERE file_path = ?",
                (file_path,),
            )
            deleted = cursor.rowcount
            conn.commit()
            return deleted
        finally:
            conn.close()

    def count(self) -> int:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM longterm_embeddings")
            return cursor.fetchone()[0]
        finally:
            conn.close()


def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> List[Tuple[str, int, int]]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        chunks.append((chunk, start, end))
        start = end - overlap
        if start < 0:
            start = end
    return chunks


_embedding_model: Optional[EmbeddingModel] = None
_embedding_store: Optional[EmbeddingStore] = None


def get_embedding_model() -> EmbeddingModel:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = EmbeddingModel()
    return _embedding_model


def get_embedding_store() -> EmbeddingStore:
    global _embedding_store
    if _embedding_store is None:
        _embedding_store = EmbeddingStore()
    return _embedding_store


def reset_embeddings():
    global _embedding_model, _embedding_store
    _embedding_model = None
    _embedding_store = None
