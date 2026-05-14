"""Versioned prompt builders for LLM enrichment jobs."""

from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

Messages = List[dict]
_SYSTEM = "system"
_USER = "user"
_TOPIC_WORD = re.compile(r"[a-z0-9]+(?:['_-][a-z0-9]+)?", re.IGNORECASE)
_TOPIC_STOPWORDS = {
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
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "them",
    "these",
    "they",
    "this",
    "those",
    "to",
    "was",
    "were",
    "with",
    "you",
    "your",
}


def clean_topic_keywords(keywords: List[str]) -> List[str]:
    """Normalize topic keywords before deterministic or LLM labeling."""
    seen: set[str] = set()
    cleaned: List[str] = []
    for raw in keywords:
        for token in _TOPIC_WORD.findall(str(raw).lower()):
            if len(token) <= 1 or token in _TOPIC_STOPWORDS or token in seen:
                continue
            seen.add(token)
            cleaned.append(token)
    return cleaned


def thread_analysis_prompt(
    title: str,
    subreddit: str,
    comments: List[dict],
) -> Tuple[Messages, str]:
    """
    Prompt to summarize the range of positions in a Reddit thread.

    Each comment dict should have keys: label, confidence, preview.
    Returns (messages, prompt_version).
    """
    comment_lines = []
    for i, c in enumerate(comments[:20], 1):
        label = c.get("label", "unknown")
        preview = (c.get("preview") or "")[:200].replace("\n", " ")
        comment_lines.append(f"{i}. [{label}] {preview}")

    comment_block = "\n".join(comment_lines) if comment_lines else "(no comments with sentiment data)"

    messages: Messages = [
        {
            "role": _SYSTEM,
            "content": (
                "You are an analyst summarizing Reddit discussion threads. "
                "Write 2-3 concise sentences identifying the main positions and any disagreements. "
                "Be factual and neutral. Do not editorialize."
            ),
        },
        {
            "role": _USER,
            "content": (
                f"Thread: \"{title}\" in r/{subreddit}\n\n"
                f"Top comments (sentiment label + text preview):\n{comment_block}\n\n"
                "Summarize the range of positions expressed in this thread."
            ),
        },
    ]
    return messages, "ta-v1"


def narrative_summary_prompt(
    date: str,
    subreddit: str,
    magnitude: float,
    top_terms: List[str],
) -> Tuple[Messages, str]:
    """
    Prompt to generate a title and summary for a detected sentiment-shift event.
    Returns (messages, prompt_version).
    """
    direction = "positive" if magnitude >= 0 else "negative"
    terms_str = ", ".join(top_terms[:8]) if top_terms else "unknown topics"

    messages: Messages = [
        {
            "role": _SYSTEM,
            "content": (
                "You are an analyst writing brief intelligence summaries about Reddit sentiment shifts. "
                "Respond with exactly two lines: "
                "Line 1: a short event title (max 10 words). "
                "Line 2: a 1-sentence explanation of the likely cause or context."
            ),
        },
        {
            "role": _USER,
            "content": (
                f"On {date}, r/{subreddit} experienced a {direction} sentiment shift "
                f"(magnitude: {magnitude:+.2f}). "
                f"Top discussed topics: {terms_str}.\n\n"
                "Write the event title and summary."
            ),
        },
    ]
    return messages, "ne-v1"


def analyst_brief_prompt(
    events: List[dict],
    topic_labels: List[str],
    model_count: int,
    parent_context: Optional[List[dict]] = None,
    evidence_context: Optional[dict] = None,
) -> Tuple[Messages, str]:
    """
    Prompt to generate a structured analyst brief as JSON.

    Returns (messages, prompt_version).
    """
    event_lines = []
    for e in events[:5]:
        label = e.get("label") or e.get("auto_label") or "Unnamed event"
        date = e.get("peak_date") or e.get("date") or ""
        event_id = e.get("event_id")
        event_prefix = f"event_id={event_id} " if event_id is not None else ""
        event_lines.append(f"- {event_prefix}{date}: {label}")

    events_block = "\n".join(event_lines) if event_lines else "No recent events."
    topics_block = ", ".join(topic_labels[:10]) if topic_labels else "No topics labeled yet."

    parent_lines: List[str] = []
    for parent in (parent_context or [])[:10]:
        pid = parent.get("display_name") or parent.get("id") or "Unknown"
        volume = parent.get("volume") or 0
        mean = parent.get("mean_sentiment")
        mean_str = f"{mean:+.2f}" if isinstance(mean, (int, float)) else "n/a"
        parent_lines.append(f"- {pid}: {volume:,} Reddit items/comments, mean sentiment {mean_str}")
    parents_block = "\n".join(parent_lines) if parent_lines else "No parent context."

    evidence_block = json.dumps(evidence_context or {}, sort_keys=True, default=str, indent=2)

    schema = (
        '{"headline": "...",'
        ' "sections": ['
        '{"title": "Executive Summary", "body": "...",'
        ' "claims": ["..."],'
        ' "evidence": [{"anchor_type": "event_id|post_id|comment_id|topic_label", "anchor_id": "...", "label": "...", "snippet": "..."}],'
        ' "drivers": ["..."],'
        ' "implications": ["..."],'
        ' "delta": "...",'
        ' "delta_source": "latest_30_vs_prior_30|narrative_events.sentiment_delta|proxy",'
        ' "current_window": "...",'
        ' "comparison_window": "...",'
        ' "evidence_gap": "..."}'
        "]}"
    )

    messages: Messages = [
        {
            "role": _SYSTEM,
            "content": (
                "You are an intelligence analyst summarizing trends from Reddit AI-community data. "
                "Respond with a single JSON object only. No markdown, no preamble. "
                f"The object MUST match this schema: {schema}. "
                "The headline is one punchy, specific sentence that names the dominant trend. "
                "Include five sections: Executive Summary, Key Findings, Notable Trends, Risks & Anomalies, Outlook. "
                "Each section body MUST be 4-6 sentences, rich with named subreddits, topics, dates, and magnitudes "
                "drawn from the provided context. Do not pad with generic statements — every sentence must assert "
                "something specific. "
                "Every major claim must cite only evidence anchors supplied in the evidence context; "
                "populate claims[], drivers[], and implications[] with at least 2 concrete items each. "
                "If evidence is thin or conflicting, say so in evidence_gap instead of inventing support."
            ),
        },
        {
            "role": _USER,
            "content": (
                f"Recent sentiment events:\n{events_block}\n\n"
                f"Active discussion topics: {topics_block}\n\n"
                f"Parent community context (last 30 days):\n{parents_block}\n\n"
                f"Evidence context and allowed anchors:\n{evidence_block}\n\n"
                f"Configured LLM models: {model_count}\n\n"
                "Generate the analyst brief JSON. Populate all fields: drivers/causes, implications, "
                "evidence anchors with snippets, delta values with delta_source/current_window/comparison_window."
            ),
        },
    ]
    return messages, "ab-v4"


def topic_label_prompt(keywords: List[str]) -> Tuple[Messages, str]:
    """
    Prompt to generate a short human-readable label for a BERTopic cluster.
    Returns (messages, prompt_version).
    """
    clean_keywords = clean_topic_keywords(keywords)
    kw_str = ", ".join(clean_keywords[:12]) if clean_keywords else "(no keywords)"

    messages: Messages = [
        {
            "role": _SYSTEM,
            "content": (
                "You label Reddit discussion clusters for an AI-community analytics dashboard. "
                "Given cleaned keywords from a BERTopic cluster, infer the specific underlying discussion theme "
                "and express it as a short, meaningful headline (2-5 words, Title Case). "
                "The label should name the subject, not describe the act of discussing it. "
                "Prefer noun phrases that a reader would immediately understand (e.g. 'Model Context Window Limits', "
                "'Open-Source Fine-Tuning', 'AI Safety Debates'). "
                "Do NOT echo keywords verbatim, do NOT use markdown or punctuation, and avoid generic filler "
                "words like Discussion, Topic, Reddit, General, Community, or Miscellaneous."
            ),
        },
        {
            "role": _USER,
            "content": f"Keywords: {kw_str}\n\nLabel:",
        },
    ]
    return messages, "tl-v3"
