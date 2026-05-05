"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { TopicBarChart } from "@/components/charts/TopicBarChart";
import { TopicGraph } from "@/components/charts/TopicGraph";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useFilterStore } from "@/lib/store";
import type { Topic, TopicGraphResponse, TopicOverTime } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function buildGraphQuery(subreddits: string[], n: number, minSimilarity: number) {
  const params = new URLSearchParams({
    n: String(n),
    min_similarity: String(minSimilarity),
  });
  subreddits.forEach((subreddit) => params.append("subreddits", subreddit));
  return `/api/topics/graph?${params}`;
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

export default function TopicsPage() {
  const { subreddits } = useFilterStore();
  const { data: topics } = useSWR<Topic[]>("/api/topics", fetcher);
  const { data: emerging } = useSWR<Topic[]>("/api/topics/emerging", fetcher);
  const { data: graph } = useSWR<TopicGraphResponse>(buildGraphQuery(subreddits, 60, 0.12), fetcher);
  const [selected, setSelected] = useState<number | null>(null);

  const emergingIds = new Set((emerging ?? []).map((t) => t.topic_id));
  const hasSubredditFilter = subreddits.length > 0;
  const graphNodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
  const graphEdges = Array.isArray(graph?.edges) ? graph.edges : [];
  const topicRows = useMemo(() => graphNodes.length || hasSubredditFilter ? graphNodes : topics ?? [], [graphNodes, hasSubredditFilter, topics]);

  useEffect(() => {
    if (selected == null && topicRows.length) {
      setSelected(topicRows[0].topic_id);
      return;
    }
    if (selected != null && topicRows.length && !topicRows.some((topic) => topic.topic_id === selected)) {
      setSelected(topicRows[0].topic_id);
    }
  }, [selected, topicRows]);

  const selectedTopic = topicRows.find((t) => t.topic_id === selected);
  const { data: overTime } = useSWR<TopicOverTime[]>(
    selected !== null ? `/api/topics/${selected}/over-time` : null,
    fetcher
  );

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Topics"
        title="Topic explorer"
        subtitle={hasSubredditFilter ? `Graph filtered to ${subreddits.join(", ")}.` : "Browse discovered topics and inspect weekly volume."}
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.55fr)_420px]">
        <ChartCard title="Topic similarity graph" subtitle="Keyword-linked clusters with selectable force layout">
          {graphNodes.length ? (
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
          <ChartCard title="Topics" subtitle="Ordered by document count">
            <div className="flex max-h-[520px] flex-col gap-1 overflow-y-auto pr-1">
              {topicRows.length ? topicRows.map((t) => (
                <button
                  key={t.topic_id}
                  onClick={() => setSelected(t.topic_id)}
                  className={`grid grid-cols-[1fr_auto] items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors ${selected === t.topic_id ? "bg-signal-green/12 text-signal-green ring-1 ring-signal-green/22" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
                >
                  <span className="truncate">{t.keywords.replace(/[[\]"]/g, "").slice(0, 48)}</span>
                  <span className="flex shrink-0 items-center gap-1">
                    {emergingIds.has(t.topic_id) && <Badge variant="secondary" className="h-4 border-signal-copper/25 bg-signal-copper/10 text-[9px] text-signal-copper">new</Badge>}
                    <span className="font-mono text-xs tabular-nums">{t.doc_count.toLocaleString()}</span>
                  </span>
                </button>
              )) : <Skeleton className="h-40 w-full" />}
            </div>
          </ChartCard>

          {selectedTopic ? (
            <>
              <ChartCard title={`Topic #${selectedTopic.topic_id}`} subtitle="Weekly document count">
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
    </div>
  );
}
