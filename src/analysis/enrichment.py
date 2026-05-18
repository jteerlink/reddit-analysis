"""LLM enrichment jobs that call Ollama to generate intelligence artifacts."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from src.analysis.briefs import (
    ANALYST_BRIEF_EVIDENCE_SCHEMA_VERSION,
    _build_analyst_brief_evidence_context,
    _parse_brief_json,
    generate_analyst_brief as _generate_analyst_brief,
)
from src.analysis.db import (
    artifact_checksum,
    complete_artifact,
    enqueue_artifact,
    fail_artifact,
    get_model_registry,
    list_artifacts,
)
from src.analysis.ollama import (
    OllamaAuthError,
    OllamaConfig,
    OllamaTimeoutError,
    OllamaUnavailableError,
    discover_models,
    probe_model,
    select_model,
)
from src.analysis.prompts import (
    clean_topic_keywords,
    narrative_summary_prompt,
    thread_analysis_prompt,
    topic_label_prompt,
)
from src.db.connection import execute, is_postgres_connection, paramstyle

logger = logging.getLogger(__name__)


def _clean_llm_label(content: str) -> str:
    """Return a single UI-safe topic label from a model response."""
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
    label = first_line.strip("`*_#-–— \t\"'")
    label = " ".join(label.split())
    return label[:80]


def _topic_sample_texts(conn: Any, topic_id: int, limit: int = 6) -> list[dict]:
    """Return bounded representative text samples for a BERTopic topic."""
    marker = paramstyle()
    probability_order = "ta.probability DESC,"
    try:
        rows = execute(
            conn,
            f"""
            SELECT p.id, p.content_type,
                   COALESCE(NULLIF(p.clean_text, ''), NULLIF(src.source_text, '')) AS sample_text,
                   src.subreddit, ta.probability
            FROM topic_assignments ta
            JOIN preprocessed p ON ta.id = p.id
            LEFT JOIN (
                SELECT id, subreddit, 'post' AS content_type, COALESCE(title, content, '') AS source_text FROM posts
                UNION ALL
                SELECT id, subreddit, 'comment' AS content_type, COALESCE(content, '') AS source_text FROM comments
            ) src ON src.id = ta.id AND src.content_type = p.content_type
            WHERE ta.topic_id = {marker}
              AND COALESCE(NULLIF(p.clean_text, ''), NULLIF(src.source_text, '')) IS NOT NULL
            ORDER BY {probability_order} LENGTH(COALESCE(NULLIF(p.clean_text, ''), src.source_text)) DESC, p.id
            LIMIT {marker}
            """,
            (topic_id, limit),
        ).fetchall()
    except Exception as exc:
        logger.warning("Could not sample topic %s text for LLM label: %s", topic_id, exc)
        return []

    samples: list[dict] = []
    for row in rows:
        text = row["sample_text"] if hasattr(row, "keys") else row[2]
        if not text:
            continue
        samples.append(
            {
                "id": row["id"] if hasattr(row, "keys") else row[0],
                "content_type": row["content_type"] if hasattr(row, "keys") else row[1],
                "subreddit": row["subreddit"] if hasattr(row, "keys") else row[3],
                "text": " ".join(str(text).split())[:320],
            }
        )
    return samples


def _select_model(conn: Any, config: OllamaConfig) -> Optional[str]:
    """
    Return the best available model from the DB registry, or None if
    Ollama is not configured or no models are available.
    """
    if config.is_cloud and not config.api_key:
        logger.warning("Ollama cloud requires OLLAMA_API_KEY — skipping enrichment")
        return None

    result = discover_models(config)
    if result.error or not result.selected_model:
        logger.warning("Ollama model discovery failed: %s", result.error)
        return None

    names = [
        str(item.get("name") or item.get("model"))
        for item in result.models
        if item.get("name") or item.get("model")
    ]
    selected_model = result.selected_model
    if names:
        responsive_model = select_model(names, is_usable=lambda model: probe_model(config, model))
        if not responsive_model:
            logger.warning("No discovered Ollama models responded to probe")
            return None
        if responsive_model != selected_model:
            logger.warning("Selected model %s did not respond to probe; using %s", selected_model, responsive_model)
        selected_model = responsive_model

    registered = {row["model_name"] for row in get_model_registry(conn)}
    if registered and selected_model not in registered:
        logger.warning("Selected model %s not in registry", selected_model)

    return selected_model


def _chat_safe(config: OllamaConfig, model: str, messages: list, artifact_id: str, conn: Any) -> Optional[str]:
    """Call chat() and convert exceptions to artifact failures. Returns content or None."""
    from src.analysis.ollama import chat

    try:
        return chat(config, model, messages)
    except OllamaAuthError as exc:
        fail_artifact(conn, artifact_id, "auth_failed", str(exc))
    except OllamaTimeoutError as exc:
        fail_artifact(conn, artifact_id, "timeout", str(exc))
    except OllamaUnavailableError as exc:
        fail_artifact(conn, artifact_id, "provider_unavailable", str(exc))
    return None


def enrich_thread_analysis(
    conn: Any,
    post_id: str,
    config: OllamaConfig,
    model: str,
) -> Optional[dict]:
    """
    Generate an LLM positions summary for a Reddit thread.

    Checks idempotency via enqueue_artifact before calling Ollama. Returns the
    enriched dict (with 'positions_summary' key) or None if skipped/fails.
    """
    marker = paramstyle()

    post = execute(conn, f"SELECT id, title, subreddit FROM posts WHERE id = {marker}", (post_id,)).fetchone()
    if not post:
        logger.warning("enrich_thread_analysis: post %s not found", post_id)
        return None

    title = post["title"] if hasattr(post, "keys") else post[1]
    subreddit = post["subreddit"] if hasattr(post, "keys") else post[2]

    rows = execute(
        conn,
        f"""
        SELECT c.id, sp.label, sp.confidence, c.content AS preview
        FROM comments c
        JOIN sentiment_predictions sp ON c.id = sp.id
        WHERE c.post_id = {marker}
        ORDER BY sp.confidence ASC, c.score DESC
        LIMIT 20
        """,
        (post_id,),
    ).fetchall()

    comments = [
        {
            "label": row["label"] if hasattr(row, "keys") else row[1],
            "confidence": row["confidence"] if hasattr(row, "keys") else row[2],
            "preview": row["preview"] if hasattr(row, "keys") else row[3],
        }
        for row in rows
    ]

    messages, version = thread_analysis_prompt(title, subreddit, comments)
    source_hash = artifact_checksum({"post_id": post_id})

    artifact = enqueue_artifact(
        conn,
        kind="thread_analysis",
        source_input_hash=source_hash,
        payload={"post_id": post_id},
        provider="ollama",
        model_name=model,
        prompt_version=version,
    )
    # enqueue_artifact returns existing artifact if idempotency key already used
    if artifact.get("status") == "succeeded":
        return json.loads(artifact.get("payload") or "{}")

    artifact_id = artifact["artifact_id"]
    content = _chat_safe(config, model, messages, artifact_id, conn)
    if content is None:
        return None

    payload = {"post_id": post_id, "positions_summary": content, "model_name": model}
    complete_artifact(conn, artifact_id, payload)
    logger.info("Thread analysis enriched: post_id=%s", post_id)
    return payload


def enrich_narrative_events(
    conn: Any,
    config: OllamaConfig,
    model: str,
    limit: int = 20,
) -> int:
    """
    Enrich narrative events with LLM-generated titles and summaries.
    Skips events that already have a succeeded artifact. Returns count enriched.
    """
    try:
        rows = execute(
            conn,
            f"SELECT event_id, peak_date, sentiment_delta, dominant_subreddits, top_terms, auto_label FROM narrative_events ORDER BY ABS(COALESCE(sentiment_delta, 0)) DESC LIMIT {paramstyle()}",
            (limit,),
        ).fetchall()
    except Exception as exc:
        logger.warning("enrich_narrative_events: could not query events: %s", exc)
        return 0

    existing_artifacts = {
        a["source_input_hash"]: a
        for a in list_artifacts(conn, kind="narrative_event_summary")
        if a.get("status") == "succeeded"
    }

    count = 0
    for row in rows:
        event_id = row["event_id"] if hasattr(row, "keys") else row[0]
        peak_date = row["peak_date"] if hasattr(row, "keys") else row[1]
        delta = float((row["sentiment_delta"] if hasattr(row, "keys") else row[2]) or 0)
        subs_raw = row["dominant_subreddits"] if hasattr(row, "keys") else row[3]
        terms_raw = row["top_terms"] if hasattr(row, "keys") else row[4]

        try:
            subs = json.loads(subs_raw) if isinstance(subs_raw, str) else (subs_raw or [])
            terms = json.loads(terms_raw) if isinstance(terms_raw, str) else (terms_raw or [])
        except (ValueError, TypeError):
            subs, terms = [], []

        subreddit = subs[0] if subs else "unknown"
        source_hash = artifact_checksum({"event_id": event_id, "peak_date": peak_date})

        if source_hash in existing_artifacts:
            continue

        messages, version = narrative_summary_prompt(peak_date, subreddit, delta, terms)
        artifact = enqueue_artifact(
            conn,
            kind="narrative_event_summary",
            source_input_hash=source_hash,
            payload={"event_id": event_id},
            provider="ollama",
            model_name=model,
            prompt_version=version,
        )
        artifact_id = artifact["artifact_id"]
        if artifact.get("status") == "succeeded":
            continue

        content = _chat_safe(config, model, messages, artifact_id, conn)
        if content is None:
            continue

        lines = [l.strip() for l in content.splitlines() if l.strip()]
        llm_label = lines[0] if lines else content[:80]
        llm_summary = lines[1] if len(lines) > 1 else content

        payload = {"event_id": event_id, "llm_label": llm_label, "llm_summary": llm_summary}
        complete_artifact(conn, artifact_id, payload)

        try:
            marker = paramstyle()
            if is_postgres_connection(conn):
                execute(
                    conn,
                    f"UPDATE narrative_events SET llm_label = {marker}, llm_summary = {marker} WHERE event_id = {marker}",
                    (llm_label, llm_summary, event_id),
                )
            else:
                execute(
                    conn,
                    "UPDATE narrative_events SET llm_label = ?, llm_summary = ? WHERE event_id = ?",
                    (llm_label, llm_summary, event_id),
                )
            conn.commit()
        except Exception as exc:
            logger.warning("Could not update narrative_events columns: %s", exc)

        count += 1
        logger.info("Narrative event %s enriched", event_id)

    return count


def enrich_analyst_brief(conn: Any, config: OllamaConfig, model: str) -> Optional[dict]:
    """Generate an LLM analyst brief from recent events and topic labels."""
    return _generate_analyst_brief(conn, config, model, _chat_safe)


def enrich_topic_labels(
    conn: Any,
    config: OllamaConfig,
    model: str,
    limit: int = 50,
) -> int:
    """
    Improve cluster_labels entries with LLM-generated labels.
    Returns count of labels updated.
    """
    try:
        rows = execute(
            conn,
            f"SELECT cluster_id, keywords, doc_count FROM cluster_labels ORDER BY doc_count DESC LIMIT {paramstyle()}",
            (limit,),
        ).fetchall()
    except Exception as exc:
        logger.warning("enrich_topic_labels: could not query cluster_labels: %s", exc)
        return 0

    existing_artifacts = {
        a["source_input_hash"]: a
        for a in list_artifacts(conn, kind="topic_label_llm")
        if a.get("status") == "succeeded"
    }

    count = 0
    for row in rows:
        cluster_id = row["cluster_id"] if hasattr(row, "keys") else row[0]
        keywords_raw = row["keywords"] if hasattr(row, "keys") else row[1]

        try:
            keywords = json.loads(keywords_raw) if isinstance(keywords_raw, str) else (keywords_raw or [])
        except (ValueError, TypeError):
            keywords = []

        clean_keywords = clean_topic_keywords(keywords)
        messages, version = topic_label_prompt(clean_keywords)
        source_hash = artifact_checksum(
            {"cluster_id": cluster_id, "keywords": clean_keywords, "prompt_version": version}
        )
        if source_hash in existing_artifacts:
            continue

        artifact = enqueue_artifact(
            conn,
            kind="topic_label_llm",
            source_input_hash=source_hash,
            payload={"cluster_id": cluster_id},
            provider="ollama",
            model_name=model,
            prompt_version=version,
        )
        artifact_id = artifact["artifact_id"]
        if artifact.get("status") == "succeeded":
            continue

        content = _chat_safe(config, model, messages, artifact_id, conn)
        if content is None:
            continue

        llm_label = _clean_llm_label(content)
        complete_artifact(conn, artifact_id, {"cluster_id": cluster_id, "llm_label": llm_label})

        try:
            marker = paramstyle()
            execute(
                conn,
                f"UPDATE cluster_labels SET label = {marker} WHERE cluster_id = {marker}",
                (llm_label, cluster_id),
            )
            conn.commit()
        except Exception as exc:
            logger.warning("Could not update cluster_labels: %s", exc)

        count += 1
        logger.info("Topic %s relabeled: %s", cluster_id, llm_label)

    return count


def enrich_bertopic_labels(
    conn: Any,
    config: OllamaConfig,
    model: str,
    limit: int = 100,
) -> int:
    """Generate LLM labels for BERTopic clusters and write to topics.llm_label.

    Sibling of enrich_topic_labels (which targets the legacy cluster_labels table).
    """
    for col in ("llm_label", "llm_prompt_version"):
        try:
            execute(conn, f"ALTER TABLE topics ADD COLUMN {col} TEXT")
        except Exception:
            pass
    try:
        rows = execute(
            conn,
            f"""
            SELECT topic_id, keywords, doc_count
            FROM topics
            WHERE topic_id != -1
              AND (llm_label IS NULL OR llm_label = '')
            ORDER BY doc_count DESC
            LIMIT {paramstyle()}
            """,
            (limit,),
        ).fetchall()
    except Exception as exc:
        logger.warning("enrich_bertopic_labels: could not query topics: %s", exc)
        return 0

    existing_artifacts = {
        a["source_input_hash"]: a
        for a in list_artifacts(conn, kind="bertopic_label_llm")
        if a.get("status") == "succeeded"
    }

    marker = paramstyle()
    count = 0
    for row in rows:
        topic_id = row["topic_id"] if hasattr(row, "keys") else row[0]
        keywords_raw = row["keywords"] if hasattr(row, "keys") else row[1]

        try:
            keywords = json.loads(keywords_raw) if isinstance(keywords_raw, str) else (keywords_raw or [])
        except (ValueError, TypeError):
            keywords = []

        if not isinstance(keywords, list):
            keywords = []

        clean_keywords = clean_topic_keywords(keywords)
        samples = _topic_sample_texts(conn, int(topic_id))
        sample_texts = [sample["text"] for sample in samples]
        messages, version = topic_label_prompt(clean_keywords, sample_texts)
        source_hash = artifact_checksum(
            {
                "topic_id": int(topic_id),
                "keywords": clean_keywords,
                "sample_ids": [sample["id"] for sample in samples],
                "samples": sample_texts,
                "prompt_version": version,
            }
        )
        if source_hash in existing_artifacts:
            continue

        artifact = enqueue_artifact(
            conn,
            kind="bertopic_label_llm",
            source_input_hash=source_hash,
            payload={
                "topic_id": int(topic_id),
                "keywords": clean_keywords,
                "samples": samples,
                "prompt_version": version,
            },
            provider="ollama",
            model_name=model,
            prompt_version=version,
        )
        artifact_id = artifact["artifact_id"]
        if artifact.get("status") == "succeeded":
            continue

        content = _chat_safe(config, model, messages, artifact_id, conn)
        if content is None:
            continue

        llm_label = _clean_llm_label(content) if content.strip() else ""
        complete_artifact(
            conn,
            artifact_id,
            {
                "topic_id": int(topic_id),
                "llm_label": llm_label,
                "prompt_version": version,
                "keywords": clean_keywords,
                "samples": samples,
            },
        )

        try:
            execute(
                conn,
                f"UPDATE topics SET llm_label = {marker}, llm_prompt_version = {marker} WHERE topic_id = {marker}",
                (llm_label, version, int(topic_id)),
            )
            conn.commit()
        except Exception as exc:
            logger.warning("Could not update topics.llm_label: %s", exc)

        count += 1
        logger.info("BERTopic topic %s relabeled: %s", topic_id, llm_label)

    return count
