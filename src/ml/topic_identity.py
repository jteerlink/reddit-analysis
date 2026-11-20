"""Stable identities for fitted topic model runs."""

import hashlib
import json
from typing import List, Union

import numpy as np


def topic_model_fingerprint(
    *,
    document_ids: List[str],
    docs: List[str],
    embedding_keys: List[str],
    embeddings: np.ndarray,
    n_neighbors: int,
    n_components: int,
    min_cluster_size: int,
    nr_topics: Union[int, str],
    min_topic_size: int,
) -> str:
    """Identify a fitted topic model by config, inputs, and embedding bytes."""
    digest = hashlib.sha256()
    config = {
        "algorithm": "bertopic-v1",
        "n_neighbors": n_neighbors,
        "n_components": n_components,
        "min_cluster_size": min_cluster_size,
        "nr_topics": str(nr_topics),
        "min_topic_size": min_topic_size,
    }
    digest.update(json.dumps(config, sort_keys=True).encode("utf-8"))
    for doc_id, key, doc in zip(document_ids, embedding_keys, docs):
        digest.update(f"{doc_id}\0{key}\0{doc}".encode("utf-8"))
    digest.update(np.asarray(embeddings, dtype=np.float32).tobytes())
    return "topic:sha256:" + digest.hexdigest()
