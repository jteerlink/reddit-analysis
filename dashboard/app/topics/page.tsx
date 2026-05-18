"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { TopicBarChart } from "@/components/charts/TopicBarChart";
import { TopicGraph } from "@/components/charts/TopicGraph";
import { TopicHeatmap } from "@/components/charts/TopicHeatmap";
import { SubredditNetworkGraph } from "@/components/charts/SubredditNetworkGraph";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useFilterStore } from "@/lib/store";
import type {
  SubredditGraphResponse,
  Topic,
  TopicGraphResponse,
  TopicHeatmapResponse,
  TopicOverTime,
} from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function buildGraphQuery(
  subreddits: string[],
  parents: string[],
  n: number,
  minSimilarity: number,
) {
  const params = new URLSearchParams({
    n: String(n),
    min_similarity: String(minSimilarity),
  });
  subreddits.forEach((subreddit) => params.append("subreddits", subreddit));
  parents.forEach((parent) => params.append("parents", parent));
  return `/api/topics/graph?${params}`;
}

function buildSubredditGraphQuery(subreddits: string[], parents: string[]) {
  const params = new URLSearchParams({ days: "30", min_edge_score: "0.05" });
  subreddits.forEach((subreddit) => params.append("subreddits", subreddit));
  parents.forEach((parent) => params.append("parents", parent));
  return `/api/subreddits/graph?${params}`;
}

function TagCloud({ keywords }: { keywords: string }) {
  const words = keywords.replace(/[[\]"]/g, "").split(/[,\s]+/).filter(Boolean);
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {words.map((w, i) => (
        <span key={i} className="rounded border border-signal-copper/25 bg-signal-copper/10 px-2 py-0.5 font-mono text-xs text-signal-copper">
          {w}
        </span>
      ))}
    </div>
  );
}

type GraphMode = "subreddits" | "topics";
type TopicLensItem = { topic_id: number; label: string; count: number };

function TopicLens({
  topics,
  selectedTopic,
  onSelectTopic,
}: {
  topics: TopicLensItem[];
  selectedTopic: number | null;
  onSelectTopic: (topicId: number | null) => void;
}) {
  if (!topics.length) {
    return null;
  }

  return (
    <div className="rounded-md border border-border bg-black/14 px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <p className="command-label">Topic lens</p>
        {selectedTopic != null && (
          <button
            type="button"
            onClick={() => onSelectTopic(null)}
            className="font-mono text-[10px] text-signal-copper transition-colors hover:text-foreground"
          >
            Clear
          </button>
        )}
      </div>
      <div className="mt-2 grid grid-cols-1 gap-1.5 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
        {topics.map((topic) => {
          const active = selectedTopic === topic.topic_id;
          return (
            <button
              key={topic.topic_id}
              type="button"
              onClick={() => onSelectTopic(active ? null : topic.topic_id)}
              className={`grid grid-cols-[1fr_auto] items-center gap-2 rounded border px-2.5 py-2 text-left text-xs transition-colors ${
                active
                  ? "border-signal-green/45 bg-signal-green/10 text-foreground"
                  : "border-border text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              }`}
              title={`Topic ${topic.topic_id}`}
            >
              <span className="truncate">{topic.label}</span>
              <span className="font-mono text-[10px] tabular-nums text-muted-foreground">{topic.count}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function TopicsPage() {
  const { subreddits, parents } = useFilterStore();
  const [graphMode, setGraphMode] = useState<GraphMode>("subreddits");
  const [isolatedParent, setIsolatedParent] = useState<string | null>(null);
  const [topicFocus, setTopicFocus] = useState<number | null>(null);

  const { data: topics } = useSWR<Topic[]>("/api/topics", fetcher);
  const { data: emerging } = useSWR<Topic[]>("/api/topics/emerging", fetcher);
  const { data: subredditGraph } = useSWR<SubredditGraphResponse>(
    buildSubredditGraphQuery(subreddits, parents),
    fetcher,
  );
  const { data: graph } = useSWR<TopicGraphResponse>(
    graphMode === "topics" ? buildGraphQuery(subreddits, parents, 60, 0.12) : null,
    fetcher,
  );
  const { data: heatmap } = useSWR<TopicHeatmapResponse>("/api/topics/heatmap?n=30", fetcher);
  const [selected, setSelected] = useState<number | null>(null);

  const emergingIds = new Set((emerging ?? []).map((t) => t.topic_id));
  const hasFilter = subreddits.length > 0 || parents.length > 0;
  const graphNodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const graphEdges = Array.isArray(graph?.edges) ? graph.edges : [];
  const subredditNodes = Array.isArray(subredditGraph?.nodes) ? subredditGraph.nodes : [];
  const subredditEdges = Array.isArray(subredditGraph?.edges) ? subredditGraph.edges : [];

  const lensTopics = useMemo<TopicLensItem[]>(() => {
    const seen = new Map<number, TopicLensItem>();
    for (const node of subredditNodes) {
      for (const topic of node.top_topics) {
        const current = seen.get(topic.topic_id) ?? {
          topic_id: topic.topic_id,
          label: topic.label || `Topic ${topic.topic_id}`,
          count: 0,
        };
        current.count += 1;
        seen.set(topic.topic_id, current);
      }
    }
    return Array.from(seen.values()).sort((a, b) => b.count - a.count).slice(0, 6);
  }, [subredditNodes]);
  const showTopicLens = graphMode === "subreddits" && lensTopics.length > 0;

  const topicRows = useMemo(
    () => graphNodes.length || hasFilter ? graphNodes : topics ?? [],
    [graphNodes, hasFilter, topics],
  );

  useEffect(() => {
    if (selected == null && topicRows.length) {
      setSelected(topicRows[0].topic_id);
      return;
    }
    if (selected != null && topicRows.length && !topicRows.some((topic) => topic.topic_id === selected)) {
      setSelected(topicRows[0].topic_id);
    }
  }, [selected, topicRows]);

  useEffect(() => {
    if (topicFocus != null && !lensTopics.some((topic) => topic.topic_id === topicFocus)) {
      setTopicFocus(null);
    }
  }, [lensTopics, topicFocus]);

  useEffect(() => {
    if (graphMode !== "subreddits" && topicFocus != null) {
      setTopicFocus(null);
    }
  }, [graphMode, topicFocus]);

  const selectedTopic = topicRows.find((t) => t.topic_id === selected);
  const { data: overTime } = useSWR<TopicOverTime[]>(
    selected !== null ? `/api/topics/${selected}/over-time` : null,
    fetcher,
  );

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Topics"
        title="Topic explorer"
        subtitle={hasFilter ? `Filtered to ${[...parents, ...subreddits].join(", ")}.` : "Subreddit network coloured by parent. Edges combine shared authors and shared topics."}
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.55fr)_420px]">
        <ChartCard
          title={graphMode === "subreddits" ? "Subreddit similarity network" : "Topic similarity graph"}
          subtitle={graphMode === "subreddits"
            ? "Node = subreddit, colour = parent group. Edge thickness = author + topic overlap."
            : "Keyword-linked topic clusters (legacy view)"
          }
          action={
            <div className="flex gap-1 text-[11px]">
              {(["subreddits", "topics"] as GraphMode[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setGraphMode(m)}
                  className={`rounded px-2 py-1 transition-colors ${graphMode === m ? "bg-signal-copper/20 text-signal-copper" : "text-muted-foreground hover:text-foreground"}`}
                >
                  {m === "subreddits" ? "Subreddit network" : "Topic keywords"}
                </button>
              ))}
            </div>
          }
        >
          {graphMode === "subreddits" ? (
            subredditNodes.length ? (
              <SubredditNetworkGraph
                nodes={subredditNodes}
                edges={subredditEdges}
                selectedParent={isolatedParent}
                selectedTopic={topicFocus}
                onSelectParent={setIsolatedParent}
              />
            ) : (
              <Skeleton className="h-[520px] w-full" />
            )
          ) : graphNodes.length ? (
            <TopicGraph
              nodes={graphNodes}
              edges={graphEdges}
              selectedTopicId={selected}
              onSelectTopic={setSelected}
            />
          ) : (
            <Skeleton className="h-[520px] w-full" />
          )}
        </ChartCard>

        <div className="space-y-4">
          <ChartCard title="Topics" subtitle="Ordered by comment count">
            {showTopicLens && (
              <TopicLens topics={lensTopics} selectedTopic={topicFocus} onSelectTopic={setTopicFocus} />
            )}
            <div className={`${showTopicLens ? "mt-3" : ""} flex max-h-[520px] flex-col gap-1 overflow-y-auto pr-1`}>
              {topicRows.length ? topicRows.map((t) => {
                const label = (t as Topic).label || (t as Topic).llm_label;
                return (
                  <button
                    key={t.topic_id}
                    onClick={() => setSelected(t.topic_id)}
                    className={`grid grid-cols-[1fr_auto] items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors ${selected === t.topic_id ? "bg-signal-green/12 text-signal-green ring-1 ring-signal-green/22" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
                  >
                    <span className="truncate">{label || t.keywords.replace(/[[\]"]/g, "").slice(0, 48)}</span>
                    <span className="flex shrink-0 items-center gap-1">
                      {t.label_source && t.label_source !== "unlabeled" && (
                        <Badge variant="outline" className="h-4 text-[9px]">
                          {t.label_source === "llm_artifact" ? "LLM" : "det"}
                        </Badge>
                      )}
                      {emergingIds.has(t.topic_id) && <Badge variant="secondary" className="h-4 border-signal-copper/25 bg-signal-copper/10 text-[9px] text-signal-copper">new</Badge>}
                      <span className="font-mono text-xs tabular-nums">{t.doc_count.toLocaleString()} comments</span>
                    </span>
                  </button>
                );
              }) : <Skeleton className="h-40 w-full" />}
            </div>
          </ChartCard>

          {selectedTopic ? (
            <>
              <ChartCard
                title={selectedTopic.label || selectedTopic.llm_label || `Topic ${selectedTopic.topic_id}`}
                subtitle="Weekly comment count"
              >
                {overTime ? <TopicBarChart data={overTime} /> : <Skeleton className="h-52 w-full" />}
              </ChartCard>
              <ChartCard title="Keywords">
                <TagCloud keywords={selectedTopic.keywords} />
              </ChartCard>
            </>
          ) : (
            <div className="command-panel flex h-52 items-center justify-center text-sm text-muted-foreground">
              Select a topic to see details
            </div>
          )}
        </div>
      </div>

      <ChartCard title="Topic sentiment heatmap" subtitle="Topic x week average sentiment">
        {heatmap?.state && heatmap.state !== "ready" && (
          <div className="mb-3 rounded-md border border-signal-yellow/25 bg-signal-yellow/10 px-3 py-2 text-xs text-signal-yellow">
            {heatmap.provenance?.detail ?? heatmap.state.replace("_", " ")}
          </div>
        )}
        {heatmap ? <TopicHeatmap data={heatmap.items} /> : <Skeleton className="h-64 w-full" />}
      </ChartCard>
    </div>
  );
}
