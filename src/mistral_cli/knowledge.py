"""Semantic search and knowledge indexing for codebase."""

import hashlib
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .config import get_data_dir


@dataclass
class IndexConfig:
    """Configuration for semantic indexing."""

    extensions: tuple[str, ...] = (
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".md",
        ".rst",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
    )
    chunk_size: int = 512  # characters per chunk
    chunk_overlap: int = 50
    model_name: str = "all-MiniLM-L6-v2"
    max_files: int = 1000
    skip_dirs: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                ".git",
                ".svn",
                ".hg",
                "__pycache__",
                "node_modules",
                ".venv",
                "venv",
                "env",
                ".env",
                "dist",
                "build",
                ".tox",
                ".pytest_cache",
                ".mypy_cache",
                "eggs",
                "*.egg-info",
            }
        )
    )


@dataclass
class SearchResult:
    """A semantic search result."""

    file_path: str
    chunk_text: str
    score: float
    line_start: int
    line_end: int


class Embedder:
    """Handles text embedding using sentence-transformers."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """Initialize the embedder.

        Args:
            model_name: The sentence-transformers model to use.
        """
        self.model_name = model_name
        self._model = None

    @property
    def model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install mistral-cli[rag]"
                )
        return self._model

    def embed(self, texts: list[str]) -> "np.ndarray":
        """Embed a list of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            Numpy array of embeddings.
        """
        import numpy as np

        return self.model.encode(texts, show_progress_bar=False)

    def embed_single(self, text: str) -> "np.ndarray":
        """Embed a single text.

        Args:
            text: Text string to embed.

        Returns:
            Numpy array of the embedding.
        """
        return self.embed([text])[0]

    @staticmethod
    def is_available() -> bool:
        """Check if sentence-transformers is installed.

        Returns:
            True if available, False otherwise.
        """
        try:
            import sentence_transformers  # noqa: F401

            return True
        except ImportError:
            return False


class CodebaseIndex:
    """SQLite-backed semantic index for a codebase."""

    def __init__(self, project_path: str, config: Optional[IndexConfig] = None):
        """Initialize the codebase index.

        Args:
            project_path: Path to the project root.
            config: Index configuration.
        """
        self.project_path = Path(project_path).resolve()
        self.config = config or IndexConfig()
        self._embedder: Optional[Embedder] = None

        # Index storage location
        project_hash = hashlib.md5(str(self.project_path).encode()).hexdigest()[:12]
        self.index_dir = get_data_dir() / "index" / project_hash
        self.db_path = self.index_dir / "index.db"

    @property
    def embedder(self) -> Embedder:
        """Get or create the embedder instance."""
        if self._embedder is None:
            self._embedder = Embedder(self.config.model_name)
        return self._embedder

    def build(
        self, progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> dict[str, Any]:
        """Build or rebuild the semantic index.

        Args:
            progress_callback: Optional callback(current, total, filename).

        Returns:
            Statistics dict with files_indexed, chunks_created, time_taken.
        """
        import numpy as np

        start_time = time.time()

        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Initialize database
        conn = sqlite3.connect(self.db_path)
        self._init_db(conn)

        # Collect files to index
        files = self._collect_files()
        if progress_callback:
            progress_callback(0, len(files), "Starting...")

        chunks_created = 0
        for i, file_path in enumerate(files):
            if progress_callback:
                progress_callback(i + 1, len(files), file_path.name)

            try:
                chunks = self._chunk_file(file_path)
                if chunks:
                    embeddings = self.embedder.embed([c["text"] for c in chunks])
                    self._store_chunks(conn, file_path, chunks, embeddings)
                    chunks_created += len(chunks)
            except Exception:
                continue  # Skip problematic files

        # Store metadata
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("created_at", str(time.time())),
        )
        conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            ("project_path", str(self.project_path)),
        )

        conn.commit()
        conn.close()

        return {
            "files_indexed": len(files),
            "chunks_created": chunks_created,
            "time_taken": time.time() - start_time,
            "index_path": str(self.index_dir),
        }

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Search the index semantically.

        Args:
            query: Natural language query.
            top_k: Maximum results to return.

        Returns:
            List of SearchResult objects sorted by relevance.
        """
        import numpy as np

        if not self.db_path.exists():
            return []

        query_embedding = self.embedder.embed_single(query)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT file_path, chunk_text, embedding, line_start, line_end FROM chunks"
        )

        results = []
        for row in cursor:
            file_path, chunk_text, emb_bytes, line_start, line_end = row
            stored_embedding = np.frombuffer(emb_bytes, dtype=np.float32)

            # Cosine similarity (embeddings are normalized by sentence-transformers)
            score = float(np.dot(query_embedding, stored_embedding))

            results.append(
                SearchResult(
                    file_path=file_path,
                    chunk_text=chunk_text,
                    score=score,
                    line_start=line_start,
                    line_end=line_end,
                )
            )

        conn.close()

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def get_stats(self) -> Optional[dict[str, Any]]:
        """Get index statistics.

        Returns:
            Statistics dict or None if no index exists.
        """
        if not self.db_path.exists():
            return None

        conn = sqlite3.connect(self.db_path)

        cursor = conn.execute("SELECT COUNT(*), COUNT(DISTINCT file_path) FROM chunks")
        chunks, files = cursor.fetchone()

        cursor = conn.execute("SELECT value FROM metadata WHERE key = 'created_at'")
        row = cursor.fetchone()
        created_at = float(row[0]) if row else None

        conn.close()

        return {
            "chunks": chunks,
            "files": files,
            "created_at": created_at,
            "path": str(self.index_dir),
        }

    def is_stale(self, max_age_days: int = 7) -> bool:
        """Check if the index is stale.

        Args:
            max_age_days: Maximum age in days before considered stale.

        Returns:
            True if index is stale or doesn't exist.
        """
        stats = self.get_stats()
        if not stats or not stats.get("created_at"):
            return True

        age_seconds = time.time() - stats["created_at"]
        age_days = age_seconds / (60 * 60 * 24)
        return age_days > max_age_days

    def _init_db(self, conn: sqlite3.Connection) -> None:
        """Initialize database schema."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY,
                file_path TEXT NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding BLOB NOT NULL,
                line_start INTEGER,
                line_end INTEGER
            )
        """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_file ON chunks(file_path)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """
        )
        # Clear existing chunks for rebuild
        conn.execute("DELETE FROM chunks")

    def _collect_files(self) -> list[Path]:
        """Collect files to index."""
        files = []

        for root, dirs, filenames in os.walk(self.project_path):
            # Filter out skip directories
            dirs[:] = [d for d in dirs if d not in self.config.skip_dirs]

            for filename in filenames:
                if Path(filename).suffix in self.config.extensions:
                    files.append(Path(root) / filename)
                    if len(files) >= self.config.max_files:
                        return files

        return files

    def _chunk_file(self, file_path: Path) -> list[dict]:
        """Split a file into overlapping chunks.

        Args:
            file_path: Path to the file.

        Returns:
            List of chunk dictionaries with text and line info.
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        chunks = []
        lines = content.split("\n")
        current_chunk: list[str] = []
        current_line_start = 1

        for i, line in enumerate(lines, 1):
            current_chunk.append(line)
            chunk_text = "\n".join(current_chunk)

            if len(chunk_text) >= self.config.chunk_size:
                chunks.append(
                    {
                        "text": chunk_text,
                        "line_start": current_line_start,
                        "line_end": i,
                    }
                )
                # Overlap: keep some lines
                overlap_lines = max(1, len(current_chunk) // 4)
                current_chunk = current_chunk[-overlap_lines:]
                current_line_start = i - overlap_lines + 1

        # Final chunk
        if current_chunk:
            chunks.append(
                {
                    "text": "\n".join(current_chunk),
                    "line_start": current_line_start,
                    "line_end": len(lines),
                }
            )

        return chunks

    def _store_chunks(
        self,
        conn: sqlite3.Connection,
        file_path: Path,
        chunks: list[dict],
        embeddings: "np.ndarray",
    ) -> None:
        """Store chunks and embeddings in database.

        Args:
            conn: Database connection.
            file_path: Path to the source file.
            chunks: List of chunk dictionaries.
            embeddings: Numpy array of embeddings.
        """
        try:
            rel_path = str(file_path.relative_to(self.project_path))
        except ValueError:
            rel_path = str(file_path)

        for chunk, embedding in zip(chunks, embeddings):
            conn.execute(
                "INSERT INTO chunks (file_path, chunk_text, embedding, line_start, line_end) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    rel_path,
                    chunk["text"],
                    embedding.astype("float32").tobytes(),
                    chunk["line_start"],
                    chunk["line_end"],
                ),
            )
