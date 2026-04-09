"""
ML Layer — Text Preprocessing & Embedding Generation

Cleans raw Reddit text and generates sentence embeddings using
all-MiniLM-L6-v2, accelerated via MPS on Apple Silicon.
"""

import json
import logging
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

    def clean(self, text: str) -> str:
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
        if self._cache_path.exists() and self._index_path.exists():
            embeddings = np.load(str(self._cache_path))
            with open(self._index_path) as f:
                index = json.load(f)
            logger.info("Loaded embedding cache: %d vectors", len(embeddings))
            return embeddings, index
        return None, {}

    def save_cache(self, embeddings: np.ndarray, index: Dict[str, int]) -> None:
        tmp_npy = self._cache_path.with_suffix(".tmp.npy")
        tmp_json = self._index_path.with_suffix(".tmp.json")
        np.save(str(tmp_npy), embeddings)
        with open(tmp_json, "w") as f:
            json.dump(index, f)
        tmp_npy.rename(self._cache_path)
        tmp_json.rename(self._index_path)
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
    all_embeddings: List[np.ndarray] = [existing_embeddings] if existing_embeddings is not None else []
    next_key = len(index)

    total = filtered = kept = 0

    conn = get_connection(db_path)
    try:
        ensure_preprocessed_table(conn)

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
                tokens = cleaner.token_count(clean_text)

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
                all_embeddings.append(batch_embeddings)
                for idx in row_indices:
                    key = str(next_key)
                    db_rows[idx][7] = key  # embedding_key
                    index[db_rows[idx][0]] = next_key  # id → row_index
                    next_key += 1

            upsert_preprocessed(conn, [tuple(r) for r in db_rows])

            # Save cache after each batch to avoid losing work
            if all_embeddings:
                combined = np.vstack(all_embeddings) if len(all_embeddings) > 1 else all_embeddings[0]
                embedder.save_cache(combined, index)
                all_embeddings = [combined]  # reset to avoid growing list

            logger.info("Batch done — total=%d filtered=%d kept=%d", total, filtered, kept)

    finally:
        conn.close()

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
