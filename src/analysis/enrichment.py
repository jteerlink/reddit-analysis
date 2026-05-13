"""LLM enrichment jobs that call Ollama to generate intelligence artifacts."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

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
    analyst_brief_prompt,
    narrative_summary_prompt,
    thread_analysis_prompt,
    topic_label_prompt,
)
from src.db.connection import execute, is_postgres_connection, paramstyle

logger = logging.getLogger(__name__)


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
    """
    Generate an LLM analyst brief from recent events and topic labels.
    Returns the brief payload or None on failure.
    """
    try:
        event_rows = execute(
            conn,
            "SELECT event_id, peak_date, llm_label, auto_label FROM narrative_events ORDER BY peak_date DESC LIMIT 5",
        ).fetchall()
    except Exception:
        event_rows = []

    events = [
        {
            "event_id": row["event_id"] if hasattr(row, "keys") else row[0],
            "date": row["peak_date"] if hasattr(row, "keys") else row[1],
            "label": (row["llm_label"] if hasattr(row, "keys") else row[2])
                     or (row["auto_label"] if hasattr(row, "keys") else row[3]),
        }
        for row in event_rows
    ]

    try:
        label_rows = execute(conn, "SELECT label FROM cluster_labels ORDER BY doc_count DESC LIMIT 10").fetchall()
        topic_labels: List[str] = [
            (row["label"] if hasattr(row, "keys") else row[0]) for row in label_rows
        ]
    except Exception:
        topic_labels = []

    try:
        model_count = int(
            execute(conn, "SELECT COUNT(*) FROM llm_model_registry WHERE available = 1").fetchone()[0] or 0
        )
    except Exception:
        model_count = 0

    parent_context: list[dict] = []
    try:
        from src.api.db import get_subreddit_categories

        parent_context = (get_subreddit_categories(days=30) or {}).get("parents", [])
    except Exception:
        logger.exception("Failed to load parent_context for analyst brief")
        parent_context = []

    parent_fingerprint = [
        {
            "id": p.get("id"),
            "volume": p.get("volume"),
            "mean_sentiment": round(p["mean_sentiment"], 2) if isinstance(p.get("mean_sentiment"), (int, float)) else None,
        }
        for p in parent_context
    ]
    source_hash = artifact_checksum(
        {
            "events": [e["event_id"] for e in events],
            "topic_count": len(topic_labels),
            "parents": parent_fingerprint,
        }
    )
    existing = [a for a in list_artifacts(conn, kind="analyst_brief_llm") if a.get("source_input_hash") == source_hash and a.get("status") == "succeeded"]
    if existing:
        return json.loads(existing[0].get("payload") or "{}")

    messages, version = analyst_brief_prompt(events, topic_labels, model_count, parent_context=parent_context)
    artifact = enqueue_artifact(
        conn,
        kind="analyst_brief_llm",
        source_input_hash=source_hash,
        payload={},
        provider="ollama",
        model_name=model,
        prompt_version=version,
    )
    artifact_id = artifact["artifact_id"]
    if artifact.get("status") == "succeeded":
        return json.loads(artifact.get("payload") or "{}")

    content = _chat_safe(config, model, messages, artifact_id, conn)
    if content is None:
        return None

    structured = _parse_brief_json(content)
    if structured is not None:
        payload = {
            "brief_id": artifact_id[:8],
            "period": "latest",
            "headline": structured.get("headline") or "Reddit Intelligence Brief",
            "sections": structured.get("sections") or [],
            "source_events": [e["event_id"] for e in events],
            "model_name": model,
        }
    else:
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        headline = lines[0] if lines else "Reddit Intelligence Brief"
        body = "\n".join(lines[1:]) if len(lines) > 1 else content
        payload = {
            "brief_id": artifact_id[:8],
            "period": "latest",
            "headline": headline,
            "sections": [{"title": "Analysis", "body": body}],
            "source_events": [e["event_id"] for e in events],
            "model_name": model,
        }
    complete_artifact(conn, artifact_id, payload)
    logger.info("Analyst brief enriched via %s", model)
    return payload


def _parse_brief_json(content: str) -> Optional[dict]:
    """Parse an ab-v2 JSON brief response. Returns None when the response isn't valid JSON."""
    text = content.strip()
    if not text:
        return None
    # Strip optional ```json fences
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json\n"):
            text = text[5:]
    # Best-effort isolation of the first JSON object if the model prefixed prose.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    sections = parsed.get("sections")
    if not isinstance(sections, list):
        return None
    cleaned: list[dict] = []
    for entry in sections:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        body = str(entry.get("body") or "").strip()
        if title and body:
            cleaned.append({"title": title, "body": body})
    if not cleaned:
        return None
    return {
        "headline": str(parsed.get("headline") or "").strip() or None,
        "sections": cleaned,
    }


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

        source_hash = artifact_checksum({"cluster_id": cluster_id, "keywords": keywords})
        if source_hash in existing_artifacts:
            continue

        messages, version = topic_label_prompt(keywords)
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

        llm_label = content.strip().splitlines()[0][:80]
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

        source_hash = artifact_checksum({"topic_id": int(topic_id), "keywords": keywords})
        if source_hash in existing_artifacts:
            continue

        messages, version = topic_label_prompt(keywords)
        artifact = enqueue_artifact(
            conn,
            kind="bertopic_label_llm",
            source_input_hash=source_hash,
            payload={"topic_id": int(topic_id)},
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

        llm_label = content.strip().splitlines()[0][:80] if content.strip() else ""
        complete_artifact(
            conn,
            artifact_id,
            {"topic_id": int(topic_id), "llm_label": llm_label, "prompt_version": version},
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
