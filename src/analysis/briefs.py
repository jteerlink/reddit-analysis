"""Analyst brief evidence enrichment helpers."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from src.analysis.db import artifact_checksum, complete_artifact, enqueue_artifact, list_artifacts
from src.analysis.ollama import OllamaConfig
from src.analysis.prompts import analyst_brief_prompt
from src.db.connection import execute, is_postgres_connection

logger = logging.getLogger(__name__)

ANALYST_BRIEF_EVIDENCE_SCHEMA_VERSION = 3
ANALYST_BRIEF_PROMPT_VERSION = "ab-v4"
BRIEF_SECTION_EXTRA_KEYS = {
    "claims",
    "evidence",
    "drivers",
    "implications",
    "delta",
    "delta_source",
    "current_window",
    "comparison_window",
    "evidence_gap",
    "observations",
    "hypotheses",
    "unknowns",
}
ANCHOR_TYPES = {"event_id", "post_id", "comment_id", "topic_label"}
_CAUSAL_LANGUAGE = (
    "cause", "caused", "because", "due to", "driven by", "led to",
    "resulted in", "churn", "retention",
    "market share", "engagement collapse", "community collapse",
)
_CAUSAL_VERB = re.compile(
    r"\b(?:driv(?:e|es|en|ing)|boost(?:ed|s|ing)?|trigger(?:ed|s|ing)?|fuel(?:ed|s|ing)?|"
    r"explain(?:ed|s|ing)?|reflect(?:ed|s|ing)?|follow(?:ed|s|ing)?)\b"
)
_HYPOTHESIS_LANGUAGE = (
    "may ", "might ", "could ", "possible", "possibly", "perhaps", "hypothesis",
    "unclear", "unknown", "cannot establish", "not enough evidence",
)


def generate_analyst_brief(
    conn: Any,
    config: OllamaConfig,
    model: str,
    chat_safe: Callable[[OllamaConfig, str, list, str, Any], Optional[str]],
) -> Optional[dict]:
    """
    Generate an LLM analyst brief from recent events and topic labels.
    Returns the brief payload or None on failure.
    """
    try:
        event_rows = execute(
            conn,
            """
            SELECT event_id, start_date, end_date, peak_date, sentiment_delta,
                   dominant_subreddits, top_terms, top_post_ids, llm_label, auto_label
            FROM narrative_events
            ORDER BY peak_date DESC, ABS(COALESCE(sentiment_delta, 0)) DESC
            LIMIT 8
            """,
        ).fetchall()
    except Exception:
        event_rows = []

    events = [
        {
            "event_id": row["event_id"] if hasattr(row, "keys") else row[0],
            "start_date": row["start_date"] if hasattr(row, "keys") else row[1],
            "end_date": row["end_date"] if hasattr(row, "keys") else row[2],
            "date": row["peak_date"] if hasattr(row, "keys") else row[3],
            "sentiment_delta": row["sentiment_delta"] if hasattr(row, "keys") else row[4],
            "dominant_subreddits": _json_array(row["dominant_subreddits"] if hasattr(row, "keys") else row[5]),
            "top_terms": _json_array(row["top_terms"] if hasattr(row, "keys") else row[6]),
            "top_post_ids": _json_array(row["top_post_ids"] if hasattr(row, "keys") else row[7]),
            "label": (row["llm_label"] if hasattr(row, "keys") else row[8])
                     or (row["auto_label"] if hasattr(row, "keys") else row[9]),
        }
        for row in event_rows
    ]

    try:
        label_rows = execute(conn, "SELECT label FROM cluster_labels ORDER BY doc_count DESC LIMIT 15").fetchall()
        topic_labels: list[str] = [
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
    evidence_bundle = _build_analyst_brief_evidence_context(events, topic_labels, parent_context, conn=conn)
    source_hash = artifact_checksum(
        {
            "prompt_version": ANALYST_BRIEF_PROMPT_VERSION,
            "evidence_schema_version": ANALYST_BRIEF_EVIDENCE_SCHEMA_VERSION,
            "events": [e["event_id"] for e in events],
            "topic_count": len(topic_labels),
            "parents": parent_fingerprint,
            "evidence_context_hash": evidence_bundle["fingerprint"],
        }
    )
    existing = [a for a in list_artifacts(conn, kind="analyst_brief_llm") if a.get("source_input_hash") == source_hash and a.get("status") == "succeeded"]
    if existing:
        return json.loads(existing[0].get("payload") or "{}")

    messages, version = analyst_brief_prompt(
        events,
        topic_labels,
        model_count,
        parent_context=parent_context,
        evidence_context=evidence_bundle["context_payload"],
    )
    artifact = enqueue_artifact(
        conn,
        kind="analyst_brief_llm",
        source_input_hash=source_hash,
        payload={},
        provider="ollama",
        model_name=model,
        prompt_version=version,
        schema_version=ANALYST_BRIEF_EVIDENCE_SCHEMA_VERSION,
    )
    artifact_id = artifact["artifact_id"]
    if artifact.get("status") == "succeeded":
        return json.loads(artifact.get("payload") or "{}")

    content = chat_safe(config, model, messages, artifact_id, conn)
    if content is None:
        return None

    structured = _parse_brief_json(
        content,
        anchor_allowlist=evidence_bundle["anchor_allowlist"],
        evidence_records=evidence_bundle["source_records"],
        allowed_numeric_values=evidence_bundle["allowed_numeric_values"],
    )
    if structured is not None:
        # Links make review possible, but parsing cannot certify semantic
        # support for freeform model prose.
        evidence_status = "unverified"
        payload = {
            "brief_id": artifact_id[:8],
            "period": "latest",
            "headline": structured.get("headline") or "Reddit Intelligence Brief",
            "sections": structured.get("sections") or [],
            "source_events": [e["event_id"] for e in events],
            "model_name": model,
            "prompt_version": version,
            "evidence_schema_version": ANALYST_BRIEF_EVIDENCE_SCHEMA_VERSION,
            "evidence_status": evidence_status,
        }
    else:
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        headline = _safe_headline(lines[0] if lines else "Reddit Intelligence Brief")
        body = _neutralize_unsupported_claims(
            "\n".join(lines[1:]) if len(lines) > 1 else content,
            evidence_bundle["source_records"],
            [],
            evidence_bundle["allowed_numeric_values"],
        )
        payload = {
            "brief_id": artifact_id[:8],
            "period": "latest",
            "headline": headline,
            "sections": [{"title": "Analysis", "body": body}],
            "source_events": [e["event_id"] for e in events],
            "model_name": model,
            "prompt_version": version,
            "evidence_schema_version": ANALYST_BRIEF_EVIDENCE_SCHEMA_VERSION,
            "evidence_status": "unverified",
        }
    complete_artifact(conn, artifact_id, payload)
    logger.info("Analyst brief enriched via %s", model)
    return payload


def _json_array(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _safe_text(value: Any, max_len: int = 500) -> str:
    return str(value or "").strip()[:max_len]


def _build_analyst_brief_evidence_context(
    events: list[dict],
    topic_labels: list[str],
    parent_context: Optional[list[dict]] = None,
    conn: Any = None,
) -> dict:
    """Return prompt context and validator allowlist from one source of truth."""
    anchor_allowlist: dict[str, set[str]] = {anchor_type: set() for anchor_type in ANCHOR_TYPES}
    context_events: list[dict] = []
    source_records: dict[str, dict] = {}

    for event in events[:5]:
        event_id = event.get("event_id")
        if event_id is not None:
            anchor_allowlist["event_id"].add(str(event_id))
        top_post_ids = [str(post_id) for post_id in event.get("top_post_ids", [])[:5] if post_id]
        anchor_allowlist["post_id"].update(top_post_ids)
        if conn is not None:
            source_records.update(_load_source_records(conn, top_post_ids, "post"))

        start_date = event.get("start_date")
        end_date = event.get("end_date")
        current_window = f"{start_date} to {end_date}" if start_date and end_date else "latest narrative event window"
        context_events.append(
            {
                "event_id": event_id,
                "label": event.get("label") or "Narrative event",
                "peak_date": event.get("date"),
                "current_window": current_window,
                "comparison_window": "prior sentiment baseline for this detected narrative event",
                "delta_source": "narrative_events.sentiment_delta",
                "sentiment_delta": event.get("sentiment_delta"),
                "top_terms": event.get("top_terms", [])[:8],
                "top_post_ids": top_post_ids,
                "dominant_subreddits": event.get("dominant_subreddits", [])[:5],
            }
        )

    topic_values = [_safe_text(label, 120) for label in topic_labels[:10] if _safe_text(label, 120)]
    anchor_allowlist["topic_label"].update(topic_values)

    context_payload = {
        "evidence_schema_version": ANALYST_BRIEF_EVIDENCE_SCHEMA_VERSION,
        "delta_baseline": {
            "preferred": "latest 30 days vs prior 30 days when explicit comparison data is available",
            "available_proxy": "narrative_events.sentiment_delta",
            "require_delta_source": True,
        },
        "events": context_events,
        "topic_labels": topic_values,
        "parent_context": (parent_context or [])[:10],
        "source_records": list(source_records.values()),
    }
    serializable_allowlist = {key: sorted(values) for key, values in anchor_allowlist.items()}
    allowed_numeric_values = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(context_payload, default=str)))
    return {
        "context_payload": context_payload,
        "anchor_allowlist": serializable_allowlist,
        "source_records": source_records,
        "allowed_numeric_values": allowed_numeric_values,
        "fingerprint": artifact_checksum({"context_payload": context_payload, "anchor_allowlist": serializable_allowlist, "source_records": source_records}),
    }


def _load_source_records(conn: Any, ids: list[str], content_type: str) -> dict[str, dict]:
    """Load bounded original records for evidence links and readable excerpts."""
    table = "posts" if content_type == "post" else "comments"
    records: dict[str, dict] = {}
    marker = "%s" if is_postgres_connection(conn) else "?"
    for record_id in ids[:20]:
        try:
            columns = "id, title, content, subreddit, timestamp, url" if table == "posts" else "id, content, subreddit, timestamp"
            row = execute(conn, f"SELECT {columns} FROM {table} WHERE id = {marker}", (record_id,)).fetchone()
        except Exception:
            # Source enrichment is optional and must never break brief creation.
            continue
        if not row:
            continue
        if table == "posts":
            original_text = row["content"] if hasattr(row, "keys") else row[2]
            title = row["title"] if hasattr(row, "keys") else row[1]
            source_url = row["url"] if hasattr(row, "keys") else row[5]
            subreddit = row["subreddit"] if hasattr(row, "keys") else row[3]
            timestamp = row["timestamp"] if hasattr(row, "keys") else row[4]
        else:
            original_text = row["content"] if hasattr(row, "keys") else row[1]
            title = None
            source_url = None
            subreddit = row["subreddit"] if hasattr(row, "keys") else row[2]
            timestamp = row["timestamp"] if hasattr(row, "keys") else row[3]
        records[f"{content_type}_id:{record_id}"] = {
            "anchor_type": f"{content_type}_id",
            "anchor_id": str(record_id),
            "original_text": str(original_text or ""),
            "title": str(title or "") or None,
            "subreddit": str(subreddit or "") or None,
            "timestamp": str(timestamp or "") or None,
            "source_url": str(source_url or f"/deep-dive?post_id={record_id}") or None,
            "content_type": content_type,
        }
    return records


def _parse_brief_json(
    content: str,
    anchor_allowlist: Optional[dict[str, list[str] | set[str]]] = None,
    evidence_records: Optional[dict[str, dict]] = None,
    allowed_numeric_values: Optional[set[str]] = None,
) -> Optional[dict]:
    """Parse an analyst brief JSON response. Returns None when the response isn't valid JSON."""
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
            section = {"title": title, "body": body}
            section.update(_clean_brief_section_extras(entry, anchor_allowlist, evidence_records))
            unsafe = _unsupported_causal_claims(section, evidence_records)
            if unsafe:
                section["evidence_gap"] = _merge_evidence_gap(
                    section.get("evidence_gap"),
                    [f"Unsupported causal or churn claim omitted: {claim}" for claim in unsafe],
                )
                for key in ("claims", "drivers", "implications", "hypotheses", "observations"):
                    if key in section:
                        section[key] = [item for item in section[key] if item not in unsafe]
                section["body"] = _neutralize_unsupported_claims(
                    section["body"], evidence_records, section.get("evidence", []), allowed_numeric_values,
                )
            else:
                section["body"] = _neutralize_unsupported_claims(
                    section["body"], evidence_records, section.get("evidence", []), allowed_numeric_values,
                )
            cleaned.append(section)
    if not cleaned:
        return None
    return {
        "headline": _safe_headline(str(parsed.get("headline") or "").strip()) or None,
        "sections": cleaned,
    }


def _safe_headline(value: str) -> str:
    """Keep headlines descriptive when the model confuses correlation with cause."""
    text = _safe_text(value, 240)
    lowered = text.lower()
    if any(term in lowered for term in _CAUSAL_LANGUAGE) or _CAUSAL_VERB.search(lowered):
        return "Latest measured sentiment signal"
    return text


def _clean_brief_section_extras(
    entry: dict,
    anchor_allowlist: Optional[dict[str, list[str] | set[str]]],
    evidence_records: Optional[dict[str, dict]] = None,
) -> dict:
    cleaned: dict[str, Any] = {}
    for key in BRIEF_SECTION_EXTRA_KEYS:
        if key not in entry:
            continue
        value = entry.get(key)
        if key in {"claims", "drivers", "implications", "observations", "hypotheses", "unknowns"}:
            items = [_safe_text(item, 240) for item in (value if isinstance(value, list) else [value])]
            cleaned[key] = [item for item in items if item]
        elif key == "evidence":
            evidence, gaps = _clean_evidence_items(value, anchor_allowlist, evidence_records)
            if evidence:
                cleaned["evidence"] = evidence
            if gaps:
                existing = cleaned.get("evidence_gap") or entry.get("evidence_gap")
                cleaned["evidence_gap"] = _merge_evidence_gap(existing, gaps)
        elif key in {"delta", "current_window", "comparison_window", "evidence_gap"}:
            text = _safe_text(value)
            if text:
                cleaned[key] = text
        elif key == "delta_source":
            text = _safe_text(value, 120)
            if text:
                cleaned[key] = text
    return cleaned


def _clean_evidence_items(
    value: Any,
    anchor_allowlist: Optional[dict[str, list[str] | set[str]]],
    evidence_records: Optional[dict[str, dict]] = None,
) -> tuple[list[dict], list[str]]:
    values = value if isinstance(value, list) else [value]
    allowed = {
        key: {str(item) for item in (items or [])}
        for key, items in (anchor_allowlist or {}).items()
    }
    cleaned: list[dict] = []
    gaps: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        anchor_type, anchor_id = _extract_anchor(item)
        if anchor_type not in ANCHOR_TYPES or not anchor_id:
            gaps.append("Evidence item omitted because it did not include a supported anchor.")
            continue
        if allowed and str(anchor_id) not in allowed.get(anchor_type, set()):
            gaps.append(f"Evidence anchor {anchor_type}:{anchor_id} was not in the supplied context.")
            continue
        cleaned_item = {
            "anchor_type": anchor_type,
            "anchor_id": str(anchor_id),
        }
        for key in ("label", "snippet", "relevance"):
            text = _safe_text(item.get(key), 300)
            if text and (key != "snippet" or evidence_records is None):
                cleaned_item[key] = text
        record = (evidence_records or {}).get(f"{anchor_type}:{anchor_id}")
        if record:
            if record.get("original_text"):
                cleaned_item["snippet"] = str(record["original_text"])[:300]
            for key in ("original_text", "title", "subreddit", "timestamp", "source_url", "content_type"):
                if record.get(key):
                    cleaned_item[key] = record[key]
        cleaned.append(cleaned_item)
    return cleaned, gaps


def _extract_anchor(item: dict) -> tuple[str, str]:
    explicit_type = item.get("anchor_type") or item.get("type")
    explicit_id = item.get("anchor_id") or item.get("id")
    if explicit_type and explicit_id:
        return str(explicit_type), str(explicit_id)
    for key in ("event_id", "post_id", "comment_id", "topic_label"):
        if item.get(key) is not None:
            return key, str(item[key])
    return "", ""


def _merge_evidence_gap(existing: Any, gaps: list[str]) -> str:
    existing_text = _safe_text(existing)
    all_gaps = ([existing_text] if existing_text else []) + gaps
    return " ".join(dict.fromkeys(gap for gap in all_gaps if gap))


def _unsupported_causal_claims(section: dict, evidence_records: Optional[dict[str, dict]]) -> list[str]:
    """Find causal/churn assertions that a sentiment delta alone cannot support."""
    candidates: list[str] = []
    for key in ("claims", "drivers", "implications", "hypotheses", "observations"):
        for item in section.get(key, []):
            text = _safe_text(item, 240)
            lowered = text.lower()
            if (
                (any(term in lowered for term in _CAUSAL_LANGUAGE) or _CAUSAL_VERB.search(lowered))
                and not any(marker in lowered for marker in _HYPOTHESIS_LANGUAGE)
            ):
                candidates.append(text)
    return list(dict.fromkeys(candidates))


def _neutralize_unsupported_claims(
    body: str,
    evidence_records: Optional[dict[str, dict]],
    evidence: list[dict],
    allowed_numeric_values: Optional[set[str]] = None,
) -> str:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", body) if part.strip()]
    retained = []
    for sentence in sentences:
        lowered = sentence.lower()
        causal = any(term in lowered for term in _CAUSAL_LANGUAGE) or _CAUSAL_VERB.search(lowered)
        unsupported_number = bool(allowed_numeric_values) and any(
            value not in allowed_numeric_values for value in re.findall(r"\d+(?:\.\d+)?", sentence)
        )
        if (causal and not any(marker in lowered for marker in _HYPOTHESIS_LANGUAGE)) or unsupported_number:
            continue
        retained.append(sentence)
    return " ".join(retained) or "Measured sentiment changed; the available evidence does not establish a cause or churn."
