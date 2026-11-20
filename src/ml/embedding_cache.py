"""Crash-safe, bounded checkpoints for the legacy embedding cache."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)
EMBEDDING_DIM = 384


def published_embedding_paths(cache_dir: Path) -> tuple[Path, Path]:
    manifest = cache_dir / "embeddings_manifest.json"
    try:
        generation = json.loads(manifest.read_text())["generation"]
    except FileNotFoundError:
        directory = cache_dir
    else:
        if not isinstance(generation, str) or len(generation) != 32 or any(
            char not in "0123456789abcdef" for char in generation
        ):
            raise ValueError("Invalid embedding generation")
        directory = cache_dir / "embedding_generations" / generation
    return directory / "embeddings_index.json", directory / "embeddings_cache.npy"


class EmbeddingCache:
    """Read-only wrapper around the published dense embedding cache."""

    def __init__(self, cache_dir: str = "models/") -> None:
        base = Path(cache_dir)
        self._index_path, self._cache_path = published_embedding_paths(base)
        self._embeddings: Optional[np.ndarray] = None
        self._index: Optional[Dict[str, int]] = None

    def load(self) -> Tuple[np.ndarray, Dict[str, int]]:
        if self._embeddings is not None and self._index is not None:
            return self._embeddings, self._index
        if not self._cache_path.exists():
            raise FileNotFoundError(f"Embedding cache not found at {self._cache_path}. Run preprocessing first.")
        if not self._index_path.exists():
            raise FileNotFoundError(f"Embedding index not found at {self._index_path}. Run preprocessing first.")
        embeddings = np.load(str(self._cache_path))
        with self._index_path.open() as stream:
            index: Dict[str, int] = json.load(stream)
        self._embeddings, self._index = embeddings, index
        return embeddings, index

    def resolve_keys(self, embedding_keys: List[str]) -> List[Optional[int]]:
        embeddings, index = self.load()
        result: List[Optional[int]] = []
        for key in embedding_keys:
            if key in index:
                result.append(index[key])
            elif str(key).lstrip("-").isdigit() and 0 <= int(key) < len(embeddings):
                result.append(int(key))
            else:
                logger.warning("Embedding key not in cache, skipping: %s", key)
                result.append(None)
        return result

    def get_subset(self, embedding_keys: List[str]) -> np.ndarray:
        embeddings, _ = self.load()
        positions = [p for p in self.resolve_keys(embedding_keys) if p is not None]
        return embeddings[positions] if positions else np.zeros((0, EMBEDDING_DIM), dtype=np.float32)


class EmbeddingCheckpointStore:
    """Append vectors in chunks, then publish one dense legacy cache."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.chunks_dir = cache_dir / "embeddings_chunks"
        self.checkpoint_path = cache_dir / "embeddings_checkpoint.json"
        self.last_consumed: List[Dict] = []

    @staticmethod
    def _atomic_save_array(path: Path, array: np.ndarray) -> None:
        tmp_path = path.with_name(f".{path.name}.tmp")
        np.save(str(tmp_path), np.asarray(array, dtype=np.float32))
        generated = Path(f"{tmp_path}.npy") if not tmp_path.name.endswith(".npy") else tmp_path
        os.replace(generated, path)

    @staticmethod
    def _atomic_save_json(path: Path, value: Dict) -> None:
        tmp_path = path.with_name(f".{path.name}.tmp")
        with tmp_path.open("w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, path)

    def _load(self) -> Dict:
        if not self.checkpoint_path.exists():
            return {"chunks": []}
        try:
            with self.checkpoint_path.open() as stream:
                value = json.load(stream)
            chunks = value.get("chunks", [])
            return {"chunks": chunks} if isinstance(chunks, list) else {"chunks": []}
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Ignoring invalid embedding checkpoint: %s", exc)
            return {"chunks": []}

    def _chunk_path(self, filename: str) -> Path:
        candidate = Path(str(filename))
        if candidate.name != str(filename) or candidate.name in {"", ".", ".."}:
            raise ValueError("Invalid embedding checkpoint filename")
        return self.chunks_dir / candidate.name

    def checkpoint_chunk(self, embeddings: np.ndarray, keys: List[str], index: Dict[str, int]) -> str:
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        checkpoint = self._load()
        filename = f"chunk-{os.urandom(12).hex()}.npy"
        path = self._chunk_path(filename)
        self._atomic_save_array(path, embeddings)
        checkpoint["chunks"].append({
            "file": filename,
            "keys": list(keys),
            "positions": [int(index[key]) for key in keys],
            "status": "pending",
        })
        self._atomic_save_json(self.checkpoint_path, checkpoint)
        return filename

    def mark_committed(self, filename: str) -> None:
        checkpoint = self._load()
        for chunk in checkpoint["chunks"]:
            if chunk.get("file") == filename:
                chunk["status"] = "committed"
        self._atomic_save_json(self.checkpoint_path, checkpoint)

    def reconcile(self, conn: Any, published_index: Dict[str, int]) -> None:
        """Resolve a crash between the database and checkpoint commits."""
        from src.db.connection import is_postgres_connection

        checkpoint = self._load()
        retained = []
        changed = False
        marker = "%s" if is_postgres_connection(conn) else "?"

        def execute(sql: str, params: Tuple[str, ...]) -> Any:
            if is_postgres_connection(conn):
                cursor = conn.cursor()
                cursor.execute(sql, params)
                return cursor
            return conn.execute(sql, params)

        for chunk in checkpoint["chunks"]:
            keys = [str(key) for key in chunk.get("keys", [])]
            try:
                path = self._chunk_path(chunk.get("file", ""))
            except ValueError:
                changed = True
                continue
            if keys and all(key in published_index for key in keys):
                path.unlink(missing_ok=True)
                changed = True
                continue
            if not keys or not path.exists():
                if keys and not path.exists():
                    placeholders = ",".join([marker] * len(keys))
                    execute(
                        f"UPDATE preprocessed SET embedding_key = NULL WHERE embedding_key IN ({placeholders})",
                        tuple(keys),
                    )
                changed = True
                continue
            placeholders = ",".join([marker] * len(keys))
            sql = f"SELECT DISTINCT embedding_key FROM preprocessed WHERE embedding_key IN ({placeholders})"
            if is_postgres_connection(conn):
                cursor = conn.cursor()
                cursor.execute(sql, tuple(keys))
                rows = cursor.fetchall()
            else:
                rows = conn.execute(sql, tuple(keys)).fetchall()
            found = {str(row[0]) for row in rows}
            if found == set(keys):
                chunk["status"] = "committed"
                retained.append(chunk)
                changed = True
            elif not found:
                path.unlink(missing_ok=True)
                changed = True
            else:
                placeholders = ",".join([marker] * len(found))
                execute(
                    f"UPDATE preprocessed SET embedding_key = NULL WHERE embedding_key IN ({placeholders})",
                    tuple(found),
                )
                path.unlink(missing_ok=True)
                changed = True
        if changed:
            conn.commit()
        checkpoint["chunks"] = retained
        if changed:
            if retained:
                self._atomic_save_json(self.checkpoint_path, checkpoint)
            else:
                self.checkpoint_path.unlink(missing_ok=True)

    def finalize(self, embeddings: Optional[np.ndarray], index: Dict[str, int]) -> Tuple[Optional[np.ndarray], Dict[str, int]]:
        checkpoint = self._load()
        chunks = []
        for chunk in checkpoint["chunks"]:
            if chunk.get("status") != "committed":
                continue
            try:
                exists = self._chunk_path(chunk.get("file", "")).exists()
            except ValueError:
                exists = False
            if exists:
                chunks.append(chunk)
        if not chunks:
            self.last_consumed = []
            return embeddings, index
        merged = [embeddings] if embeddings is not None else []
        known = set(index)
        consumed = []
        for chunk in chunks:
            path = self._chunk_path(chunk["file"])
            keys = [str(key) for key in chunk.get("keys", [])]
            vectors = np.load(str(path))
            if len(vectors) != len(keys):
                logger.warning("Leaving mismatched embedding chunk for recovery: %s", path)
                continue
            fresh = [position for position, key in enumerate(keys) if key not in known]
            if fresh:
                merged.append(np.asarray(vectors[fresh], dtype=np.float32))
                next_position = sum(len(array) for array in merged) - len(fresh)
                for position, key in enumerate(keys):
                    if key not in known:
                        index[key] = next_position
                        next_position += 1
                        known.add(key)
            consumed.append(chunk)
        self.last_consumed = consumed
        combined = np.vstack(merged) if merged else None
        if combined is not None:
            # The caller's save_cache is injected to retain the old API.
            return combined, index
        return embeddings, index

    def cleanup(self, chunks: List[Dict]) -> None:
        checkpoint = self._load()
        consumed_files = {str(chunk.get("file")) for chunk in chunks}
        for filename in consumed_files:
            try:
                self._chunk_path(filename).unlink(missing_ok=True)
            except ValueError:
                continue
        remaining = [chunk for chunk in checkpoint["chunks"]
                     if str(chunk.get("file")) not in consumed_files]
        if remaining:
            self._atomic_save_json(self.checkpoint_path, {"chunks": remaining})
        else:
            self.checkpoint_path.unlink(missing_ok=True)
            try:
                self.chunks_dir.rmdir()
            except OSError:
                pass
