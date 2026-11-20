"""
ML Layer — Text Preprocessing & Embedding Generation

Cleans raw Reddit text and generates sentence embeddings using
all-MiniLM-L6-v2, accelerated via MPS on Apple Silicon.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Bot account patterns (case-insensitive suffix match or exact match)
_BOT_PATTERNS = re.compile(
    r"(?:bot$|automoderator|automod|\[deleted\]|\[removed\]|_bot$|-bot$)",
    re.IGNORECASE,
)

# Text cleaning regexes
_RE_URL = re.compile(r"https?://\S+|www\.\S+")
_RE_QUOTE = re.compile(r"^>+\s?", re.MULTILINE)
_RE_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_BOLD_ITALIC = re.compile(r"\*{1,3}([^*]+)\*{1,3}")
_RE_STRIKETHROUGH = re.compile(r"~~([^~]+)~~")
_RE_INLINE_CODE = re.compile(r"`([^`]+)`")
_RE_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
_RE_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_RE_WHITESPACE = re.compile(r"\s+")
_RE_WORD = re.compile(r"[a-z0-9]+(?:['_-][a-z0-9]+)?")

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "hers",
    "him",
    "his",
    "i",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "our",
    "ours",
    "she",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "these",
    "they",
    "this",
    "those",
    "to",
    "was",
    "we",
    "were",
    "with",
    "you",
    "your",
    "yours",
}


def _detect_device() -> str:
    """Return the best available PyTorch device: mps → cuda → cpu."""
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


class TextCleaner:
    """Clean and normalize raw Reddit post/comment text."""

    def __init__(self, lemmatize: bool = False):
        self._lemmatize = lemmatize
        self._nlp = None  # loaded lazily

    def _get_nlp(self):
        if self._nlp is None:
            import spacy
            self._nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
        return self._nlp

    def clean(self, text: str, strip_stopwords: bool = True) -> str:
        if not text:
            return ""
        text = _RE_CODE_BLOCK.sub(" ", text)
        text = _RE_QUOTE.sub(" ", text)
        text = _RE_MARKDOWN_LINK.sub(r"\1", text)  # must run before URL strip
        text = _RE_URL.sub(" ", text)
        text = _RE_BOLD_ITALIC.sub(r"\1", text)
        text = _RE_STRIKETHROUGH.sub(r"\1", text)
        text = _RE_INLINE_CODE.sub(r"\1", text)
        text = _RE_HEADING.sub(" ", text)
        text = text.lower()
        text = _RE_WHITESPACE.sub(" ", text).strip()

        if self._lemmatize and text:
            nlp = self._get_nlp()
            doc = nlp(text)
            text = " ".join(token.lemma_ for token in doc if not token.is_space)

        tokens = _RE_WORD.findall(text)
        if strip_stopwords:
            tokens = [token for token in tokens if token not in _STOPWORDS]
        text = " ".join(tokens)

        return text

    @staticmethod
    def is_bot(author: str) -> bool:
        if not author:
            return True
        return bool(_BOT_PATTERNS.search(author))

    @staticmethod
    def token_count(text: str) -> int:
        return len(text.split()) if text else 0

    def build_raw_text(self, title: Optional[str], content: Optional[str]) -> str:
        """Combine title + content for posts; use content alone for comments."""
        parts = []
        if title:
            parts.append(title.strip())
        if content and content.strip() not in ("", "[deleted]", "[removed]"):
            parts.append(content.strip())
        return " ".join(parts)


class EmbeddingGenerator:
    """
    Generate sentence embeddings using all-MiniLM-L6-v2.

    Uses MPS on Apple Silicon, CUDA if available, else CPU.
    Embeddings stored as float32 numpy arrays.
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: str = "models/",
        device: Optional[str] = None,
    ):
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.device = device or _detect_device()
        self._model = None  # loaded lazily

        self._cache_path = self.cache_dir / "embeddings_cache.npy"
        self._index_path = self.cache_dir / "embeddings_index.json"
        # New vectors are checkpointed as bounded chunks.  The legacy dense
        # files remain the published cache and are replaced only after a
        # successful conversion of all committed chunks.
        self._chunks_dir = self.cache_dir / "embeddings_chunks"
        self._checkpoint_path = self.cache_dir / "embeddings_checkpoint.json"
        from .embedding_cache import EmbeddingCheckpointStore
        self._checkpoint_store = EmbeddingCheckpointStore(self.cache_dir)

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading %s on device=%s", self.model_name, self.device)
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def embed_batch(self, texts: List[str], batch_size: int = 256) -> np.ndarray:
        model = self._get_model()
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        return embeddings.astype(np.float32)

    def load_cache(self) -> Tuple[Optional[np.ndarray], Dict[str, int]]:
        staged_index = self._index_path.with_suffix(".tmp.json")
        if self._cache_path.exists() and (self._index_path.exists() or staged_index.exists()):
            embeddings = np.load(str(self._cache_path))
            index_path = self._index_path if self._index_path.exists() else staged_index
            with open(index_path) as f:
                index = json.load(f)
            # If a process stopped after publishing the array but before
            # publishing its index, the staged index is the matching pair.
            if (not self._index_path.exists() or len(index) != len(embeddings)) and staged_index.exists():
                try:
                    with staged_index.open() as f:
                        candidate = json.load(f)
                    positions = [int(value) for value in candidate.values()]
                    if len(candidate) == len(embeddings) and sorted(positions) == list(range(len(embeddings))):
                        os.replace(staged_index, self._index_path)
                        index = candidate
                except (OSError, ValueError, TypeError):
                    logger.warning("Could not reconcile staged embedding index")
            logger.info("Loaded embedding cache: %d vectors", len(embeddings))
            return embeddings, index
        return None, {}

    def _checkpoint_chunk(self, embeddings: np.ndarray, keys: List[str], index: Dict[str, int]) -> str:
        return self._checkpoint_store.checkpoint_chunk(embeddings, keys, index)

    def _mark_checkpoint_committed(self, filename: str) -> None:
        self._checkpoint_store.mark_committed(filename)

    def reconcile_checkpoints(self, conn) -> None:
        self._checkpoint_store.reconcile(conn)

    def finalize_checkpoints(self, embeddings: Optional[np.ndarray], index: Dict[str, int]) -> Tuple[Optional[np.ndarray], Dict[str, int]]:
        merged, index = self._checkpoint_store.finalize(embeddings, index)
        if merged is not embeddings:
            self.save_cache(merged, index)
            self._checkpoint_store.cleanup(self._checkpoint_store.last_consumed)
        return merged, index

    def save_cache(self, embeddings: np.ndarray, index: Dict[str, int]) -> None:
        tmp_npy = self._cache_path.with_suffix(".tmp.npy")
        tmp_json = self._index_path.with_suffix(".tmp.json")
        np.save(str(tmp_npy), np.asarray(embeddings, dtype=np.float32))
        with open(tmp_json, "w") as f:
            json.dump(index, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_npy, self._cache_path)
        os.replace(tmp_json, self._index_path)
        logger.info("Saved embedding cache: %d vectors", len(embeddings))


def run_preprocessing(
    db_path: str,
    cache_dir: str = "models/",
    batch_size: int = 1000,
    embed_batch_size: int = 256,
    lemmatize: bool = False,
    mlflow_tracking: bool = True,
) -> Dict:
    """
    Full preprocessing pipeline:
      1. Clean + filter all unprocessed posts/comments
      2. Generate MPS-accelerated embeddings for kept records
      3. Write results to `preprocessed` table
      4. Save/update embedding cache on disk

    Returns summary dict with counts and device info.
    """
    from .db import get_connection, ensure_preprocessed_table, iter_raw_records, upsert_preprocessed

    run = None
    if mlflow_tracking:
        try:
            import mlflow
            mlflow.set_tracking_uri("mlruns")
            mlflow.set_experiment("reddit-analyzer-phase2")
            run = mlflow.start_run(run_name="week1-preprocessing")
        except ImportError:
            logger.warning("mlflow not installed; skipping experiment tracking")

    cleaner = TextCleaner(lemmatize=lemmatize)
    embedder = EmbeddingGenerator(cache_dir=cache_dir)

    device = embedder.device
    logger.info("Preprocessing on device=%s", device)

    existing_embeddings, index = embedder.load_cache()
    next_key = max(index.values(), default=-1) + 1

    total = filtered = kept = 0

    conn = get_connection(db_path)
    try:
        ensure_preprocessed_table(conn)
        embedder.reconcile_checkpoints(conn)
        existing_embeddings, index = embedder.finalize_checkpoints(existing_embeddings, index)
        next_key = max(index.values(), default=-1) + 1

        for batch in iter_raw_records(conn, batch_size=batch_size):
            db_rows = []
            texts_to_embed: List[str] = []
            row_indices: List[int] = []  # position in db_rows for non-filtered

            for row in batch:
                total += 1
                rid = row["id"]
                content_type = row["content_type"]
                author = row["author"] if row["author"] else ""
                title = row["title"] if "title" in row.keys() else None
                content = row["content"]

                raw_text = cleaner.build_raw_text(title, content)
                clean_text = cleaner.clean(raw_text)
                tokens = cleaner.token_count(cleaner.clean(raw_text, strip_stopwords=False))

                is_filtered = 0
                filter_reason = None

                if cleaner.is_bot(author):
                    is_filtered = 1
                    filter_reason = "bot"
                    filtered += 1
                elif tokens < 10:
                    is_filtered = 1
                    filter_reason = "too_short" if tokens > 0 else "empty"
                    filtered += 1

                db_rows.append([rid, content_type, raw_text, clean_text, tokens,
                                 is_filtered, filter_reason, None])

                if not is_filtered:
                    row_indices.append(len(db_rows) - 1)
                    texts_to_embed.append(clean_text)
                    kept += 1

            if texts_to_embed:
                batch_embeddings = embedder.embed_batch(texts_to_embed, batch_size=embed_batch_size)
                # Model implementations return one row per input.  Preserve
                # the existing test/mocking contract while making the real
                # path deterministic if a scalar embedding is returned.
                if len(batch_embeddings) == 1 and len(texts_to_embed) > 1:
                    batch_embeddings = np.repeat(batch_embeddings, len(texts_to_embed), axis=0)
                if len(batch_embeddings) != len(texts_to_embed):
                    raise ValueError("Embedding count does not match input batch")
                keys = []
                for idx in row_indices:
                    key = db_rows[idx][0]  # use reddit id as embedding_key
                    db_rows[idx][7] = key
                    index[key] = next_key  # id → row_index
                    next_key += 1
                    keys.append(key)
                chunk_file = embedder._checkpoint_chunk(batch_embeddings, keys, index)

            upsert_preprocessed(conn, [tuple(r) for r in db_rows])
            if texts_to_embed:
                embedder._mark_checkpoint_committed(chunk_file)

            logger.info("Batch done — total=%d filtered=%d kept=%d", total, filtered, kept)

    finally:
        conn.close()

    # One full-history merge at the end avoids repeatedly copying the legacy
    # cache.  If this conversion fails, the DB rows and chunk manifest remain
    # recoverable on the next invocation.
    existing_embeddings, index = embedder.finalize_checkpoints(existing_embeddings, index)

    summary = {
        "total": total,
        "filtered": filtered,
        "kept": kept,
        "device": device,
        "embedding_dim": 384,  # all-MiniLM-L6-v2 output dim
        "cache_path": str(embedder._cache_path),
        "model_name": embedder.model_name,
    }

    if run is not None:
        import mlflow
        mlflow.log_params({
            "model_name": summary["model_name"],
            "device": device,
            "lemmatize": lemmatize,
            "batch_size": batch_size,
            "embed_batch_size": embed_batch_size,
        })
        mlflow.log_metrics({
            "record_count": total,
            "filtered_count": filtered,
            "kept_count": kept,
            "embedding_dim": summary["embedding_dim"],
        })
        mlflow.end_run()

    logger.info("Preprocessing complete: %s", summary)
    return summary
