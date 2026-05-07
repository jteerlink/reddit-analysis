"""CLI script: run Ollama LLM enrichment against the local database."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM enrichment jobs via Ollama")
    parser.add_argument("--db", required=True, help="Path to SQLite DB or postgres:// URL")
    parser.add_argument("--events", action="store_true", help="Enrich narrative events")
    parser.add_argument("--brief", action="store_true", help="Generate analyst brief")
    parser.add_argument("--topics", action="store_true", help="Improve topic labels")
    parser.add_argument("--thread-id", help="Enrich a specific thread by post_id")
    parser.add_argument("--all", dest="all_jobs", action="store_true", help="Run all enrichment jobs")
    parser.add_argument("--limit", type=int, default=20, help="Max items to enrich per job (default: 20)")
    args = parser.parse_args()

    from src.analysis.enrichment import (
        _select_model,
        enrich_analyst_brief,
        enrich_narrative_events,
        enrich_thread_analysis,
        enrich_topic_labels,
    )
    from src.analysis.ollama import OllamaConfig, probe_model
    from src.ml.db import get_connection

    config = OllamaConfig.from_env()

    if config.is_cloud and not config.api_key:
        logger.error("OLLAMA_API_KEY is required for cloud Ollama. Set it and retry.")
        sys.exit(1)

    conn = get_connection(args.db)

    model = _select_model(conn, config)
    if not model:
        logger.error("No Ollama model available. Check OLLAMA_BASE_URL and model registry.")
        conn.close()
        sys.exit(1)

    logger.info("Selected model: %s", model)

    if not probe_model(config, model):
        logger.error("Model %s did not respond to probe. Is Ollama running?", model)
        conn.close()
        sys.exit(1)

    logger.info("Model probe OK")

    run_events = args.all_jobs or args.events
    run_brief = args.all_jobs or args.brief
    run_topics = args.all_jobs or args.topics
    run_thread = args.thread_id

    if run_events:
        count = enrich_narrative_events(conn, config, model, limit=args.limit)
        print(f"Narrative events enriched: {count}")

    if run_thread:
        result = enrich_thread_analysis(conn, args.thread_id, config, model)
        if result:
            print(f"Thread {args.thread_id} enriched")
        else:
            print(f"Thread {args.thread_id}: enrichment skipped or failed")

    if run_brief:
        result = enrich_analyst_brief(conn, config, model)
        if result:
            print(f"Analyst brief generated: {result.get('headline', '')}")
        else:
            print("Analyst brief: enrichment failed")

    if run_topics:
        count = enrich_topic_labels(conn, config, model, limit=args.limit)
        print(f"Topic labels enriched: {count}")

    if not any([run_events, run_brief, run_topics, run_thread]):
        parser.print_help()

    conn.close()


if __name__ == "__main__":
    main()
