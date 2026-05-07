"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { ArrowRight, Maximize2, Sparkles } from "lucide-react";
import { TopicGraph } from "@/components/charts/TopicGraph";
import { useFilterStore } from "@/lib/store";
import type { Topic, TopicGraphResponse } from "@/lib/types";

interface Props {
  topics?: Topic[];
}

const DEFAULT_TOPICS = [
  { topic_id: 1, keywords: "AI regulation", doc_count: 12400, coherence_score: 0.41 },
  { topic_id: 2, keywords: "OpenAI", doc_count: 10100, coherence_score: 0.36 },
  { topic_id: 3, keywords: "Earnings", doc_count: 8700, coherence_score: -0.12 },
  { topic_id: 4, keywords: "Inflation", doc_count: 7200, coherence_score: -0.28 },
  { topic_id: 5, keywords: "Crypto", doc_count: 6800, coherence_score: 0.09 },
];

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function buildGraphQuery(subreddits: string[], n: number, minSimilarity: number) {
  const params = new URLSearchParams({
    n: String(n),
    min_similarity: String(minSimilarity),
  });
  subreddits.forEach((subreddit) => params.append("subreddits", subreddit));
  return `/api/topics/graph?${params}`;
}

function formatCount(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return value.toLocaleString();
}

function topicName(keywords: string) {
  return keywords.replace(/[[\]"]/g, "").split(",")[0].trim() || keywords.slice(0, 18);
}

export function TopicExplorerPanel({ topics }: Props) {
  const { subreddits } = useFilterStore();
  const hasSubredditFilter = subreddits.length > 0;
  const { data: graph } = useSWR<TopicGraphResponse>(buildGraphQuery(subreddits, 18, 0.1), fetcher);
  const graphNodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const graphEdges = Array.isArray(graph?.edges) ? graph.edges : [];
  const rowSource = graphNodes.slice(0, 5).length || hasSubredditFilter
    ? graphNodes.slice(0, 5)
    : topics?.slice(0, 5) ?? DEFAULT_TOPICS;
  const rows = rowSource.map((topic, index) => ({
    ...topic,
    coherence_score: topic.coherence_score ?? [0.41, 0.36, -0.12, -0.28, 0.09][index],
  }));
  const [selectedTopicId, setSelectedTopicId] = useState<number | null>(null);

  useEffect(() => {
    if (selectedTopicId == null && rows.length) {
      setSelectedTopicId(rows[0].topic_id);
      return;
    }
    if (selectedTopicId != null && rows.length && !rows.some((topic) => topic.topic_id === selectedTopicId)) {
      setSelectedTopicId(rows[0].topic_id);
    }
  }, [rows, selectedTopicId]);

  return (
    <section className="command-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="command-label">Topic Explorer</p>
          <h3 className="mt-1 text-sm font-semibold text-foreground">Signal clusters</h3>
        </div>
        <div className="flex items-center gap-2 text-muted-foreground">
          <Sparkles className="size-3.5" aria-hidden="true" />
          <Link href="/topics" aria-label="Expand topic explorer" className="transition-colors hover:text-foreground">
            <Maximize2 className="size-3.5" />
          </Link>
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-[0.95fr_1.05fr]">
        <div className="relative min-h-52 overflow-hidden rounded-lg">
          {graphNodes.length ? (
            <TopicGraph
              nodes={graphNodes}
              edges={graphEdges}
              selectedTopicId={selectedTopicId}
              onSelectTopic={setSelectedTopicId}
              compact
            />
          ) : (
            <div className="grid min-h-52 place-items-center rounded-lg border border-white/8 bg-black/20 signal-grid text-xs text-muted-foreground">
              Waiting for graph signals
            </div>
          )}
        </div>

        <div className="min-w-0">
          <div className="mb-2 flex items-center justify-between font-mono text-[10px] text-muted-foreground">
            <span>Top topics</span>
            <span>delta</span>
          </div>
          <div className="space-y-2">
            {rows.map((topic, index) => {
              const score = topic.coherence_score ?? 0;
              return (
                <div key={topic.topic_id} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 text-xs">
                  <button className="truncate text-left text-foreground hover:text-signal-green" onClick={() => setSelectedTopicId(topic.topic_id)}>{topicName(topic.keywords)}</button>
                  <span className="font-mono text-[11px] text-muted-foreground">{formatCount(topic.doc_count)}</span>
                  <span className={`font-mono text-[11px] ${score >= 0 ? "text-signal-green" : "text-signal-red"}`}>
                    {score >= 0 ? "+" : ""}{score.toFixed(2)}
                  </span>
                  {index < rows.length - 1 && <div className="col-span-3 h-px bg-border" />}
                </div>
              );
            })}
          </div>
          <Link href="/topics" className="mt-4 flex w-full items-center justify-between rounded-md border border-signal-copper/25 bg-signal-copper/8 px-3 py-2 text-xs text-signal-copper transition-colors hover:border-signal-copper/50 hover:bg-signal-copper/12">
            Explore all topics
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </section>
  );
}
