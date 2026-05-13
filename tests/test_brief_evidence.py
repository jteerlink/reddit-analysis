"""Tests for analyst brief evidence parsing helpers."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.analysis.enrichment import _build_analyst_brief_evidence_context, _parse_brief_json


def test_parse_brief_json_preserves_allowlisted_evidence_metadata():
    response = json.dumps(
        {
            "headline": "Evidence brief",
            "sections": [
                {
                    "title": "Key Findings",
                    "body": "Event 1 drove discussion.",
                    "claims": ["Event 1 drove discussion."],
                    "drivers": ["New model release"],
                    "implications": ["Developers may compare local options."],
                    "delta": "Positive sentiment increased around local models.",
                    "delta_source": "narrative_events.sentiment_delta",
                    "current_window": "2026-05-01 to 2026-05-07",
                    "comparison_window": "prior sentiment baseline for this detected narrative event",
                    "evidence": [
                        {
                            "anchor_type": "event_id",
                            "anchor_id": "1",
                            "label": "Local model spike",
                            "snippet": "Local model mentions rose.",
                        },
                        {"post_id": "p1", "label": "Benchmark post"},
                    ],
                }
            ],
        }
    )

    parsed = _parse_brief_json(
        response,
        anchor_allowlist={"event_id": {"1"}, "post_id": {"p1"}, "comment_id": set(), "topic_label": set()},
    )

    section = parsed["sections"][0]
    assert section["claims"] == ["Event 1 drove discussion."]
    assert section["drivers"] == ["New model release"]
    assert section["implications"] == ["Developers may compare local options."]
    assert section["delta_source"] == "narrative_events.sentiment_delta"
    assert section["evidence"] == [
        {
            "anchor_type": "event_id",
            "anchor_id": "1",
            "label": "Local model spike",
            "snippet": "Local model mentions rose.",
        },
        {"anchor_type": "post_id", "anchor_id": "p1", "label": "Benchmark post"},
    ]


def test_parse_brief_json_caveats_invented_post_anchor():
    response = json.dumps(
        {
            "headline": "Evidence brief",
            "sections": [
                {
                    "title": "Key Findings",
                    "body": "A claim with mixed evidence.",
                    "evidence": [
                        {"post_id": "p1", "label": "Known post"},
                        {"post_id": "p999", "label": "Invented post"},
                    ],
                }
            ],
        }
    )

    parsed = _parse_brief_json(
        response,
        anchor_allowlist={"event_id": set(), "post_id": {"p1"}, "comment_id": set(), "topic_label": set()},
    )

    section = parsed["sections"][0]
    assert section["evidence"] == [{"anchor_type": "post_id", "anchor_id": "p1", "label": "Known post"}]
    assert "post_id:p999" in section["evidence_gap"]


def test_build_analyst_brief_evidence_context_returns_payload_and_allowlist():
    bundle = _build_analyst_brief_evidence_context(
        [
            {
                "event_id": 7,
                "start_date": "2026-05-01",
                "end_date": "2026-05-07",
                "date": "2026-05-04",
                "label": "Local models surge",
                "sentiment_delta": 0.42,
                "top_terms": ["ollama", "local"],
                "top_post_ids": ["p1", "p2"],
                "dominant_subreddits": ["LocalLLaMA"],
            }
        ],
        ["Local model benchmarks"],
        [],
    )

    assert bundle["context_payload"]["events"][0]["delta_source"] == "narrative_events.sentiment_delta"
    assert bundle["anchor_allowlist"]["event_id"] == ["7"]
    assert bundle["anchor_allowlist"]["post_id"] == ["p1", "p2"]
    assert bundle["anchor_allowlist"]["topic_label"] == ["Local model benchmarks"]
    assert bundle["fingerprint"]
