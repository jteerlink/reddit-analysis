"""Versioned prompt builders for LLM enrichment jobs."""

from __future__ import annotations

from typing import List, Tuple

Messages = List[dict]
_SYSTEM = "system"
_USER = "user"


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
) -> Tuple[Messages, str]:
    """
    Prompt to generate a structured analyst brief.
    Returns (messages, prompt_version).
    """
    event_lines = []
    for e in events[:5]:
        label = e.get("label") or e.get("auto_label") or "Unnamed event"
        date = e.get("peak_date") or e.get("date") or ""
        event_lines.append(f"- {date}: {label}")

    events_block = "\n".join(event_lines) if event_lines else "No recent events."
    topics_block = ", ".join(topic_labels[:10]) if topic_labels else "No topics labeled yet."

    messages: Messages = [
        {
            "role": _SYSTEM,
            "content": (
                "You are an intelligence analyst summarizing trends from Reddit data. "
                "Write a brief with: a headline (1 line), a key findings section (2-3 bullets), "
                "and a 1-sentence outlook. Be concise and factual."
            ),
        },
        {
            "role": _USER,
            "content": (
                f"Recent sentiment events:\n{events_block}\n\n"
                f"Active discussion topics: {topics_block}\n"
                f"Configured LLM models: {model_count}\n\n"
                "Generate the analyst brief."
            ),
        },
    ]
    return messages, "ab-v1"


def topic_label_prompt(keywords: List[str]) -> Tuple[Messages, str]:
    """
    Prompt to generate a short human-readable label for a BERTopic cluster.
    Returns (messages, prompt_version).
    """
    kw_str = ", ".join(keywords[:12]) if keywords else "(no keywords)"

    messages: Messages = [
        {
            "role": _SYSTEM,
            "content": (
                "You label Reddit discussion clusters. "
                "Given a list of keywords from a topic cluster, respond with only a short label "
                "(2-5 words, title case). No explanation."
            ),
        },
        {
            "role": _USER,
            "content": f"Keywords: {kw_str}\n\nLabel:",
        },
    ]
    return messages, "tl-v1"
