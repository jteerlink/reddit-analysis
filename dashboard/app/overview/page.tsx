"use client";

import useSWR from "swr";
import { useFilterStore } from "@/lib/store";
import { MetricCard } from "@/components/shared/MetricCard";
import { ChartCard } from "@/components/shared/ChartCard";
import { ActivityFeedStrip } from "@/components/overview/ActivityFeedStrip";
import { CommandBar } from "@/components/overview/CommandBar";
import { PipelineHealthCard } from "@/components/overview/PipelineHealthCard";
import { SignalStreamChart } from "@/components/overview/SignalStreamChart";
import { TopicExplorerPanel } from "@/components/overview/TopicExplorerPanel";
import type { CollectionSummary, SentimentSummary, VolumeDaily } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function buildQuery(subreddits: string[]) {
  if (!subreddits.length) return "";
  return "?" + subreddits.map((s) => `subreddits=${encodeURIComponent(s)}`).join("&");
}

export default function OverviewPage() {
  const { subreddits, dateRange } = useFilterStore();
  const q = buildQuery(subreddits);

  const { data: summary } = useSWR<CollectionSummary>(`/api/summary${q}`, fetcher);
  const { data: sentimentData } = useSWR<SentimentSummary[]>(`/api/sentiment/summary${q}`, fetcher);
  const { data: volumeData } = useSWR<VolumeDaily[]>(`/api/volume/daily${q}`, fetcher);

  const totalPosts = summary?.total_posts?.toLocaleString() ?? "—";
  const totalComments = summary?.total_comments?.toLocaleString() ?? "—";
  const lastML = summary?.last_ml_timestamp?.slice(0, 10) ?? "—";

  const posCount = sentimentData?.find((d) => d.label === "positive")?.count ?? 0;
  const negCount = sentimentData?.find((d) => d.label === "negative")?.count ?? 0;
  const neuCount = sentimentData?.find((d) => d.label === "neutral")?.count ?? 0;
  const total = posCount + negCount + neuCount;
  const sentimentMix = total
    ? `${Math.round((posCount / total) * 100)}% pos`
    : "-";

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-4">
      <CommandBar selectedSubreddits={subreddits} dateRange={dateRange} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total posts" value={totalPosts} sub="indexed signals" />
        <MetricCard label="Total comments" value={totalComments} sub="conversation mass" />
        <MetricCard label="Last ML run" value={lastML} sub="model refresh" />
        <MetricCard label="Sentiment mix" value={sentimentMix} sub="active window" accent />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(380px,0.75fr)]">
        <SignalStreamChart volumeData={volumeData} sentimentData={sentimentData} />

        <div className="grid gap-4">
          <PipelineHealthCard />
          <TopicExplorerPanel topics={summary?.trending_topics} />
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
        <ActivityFeedStrip />

        <ChartCard title="Trending topics" subtitle="Top topics by doc count in the most recent week">
          {summary?.trending_topics?.length ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="pb-2 font-medium">Topic</th>
                  <th className="pb-2 font-medium">Keywords</th>
                  <th className="pb-2 text-right font-medium">Docs</th>
                </tr>
              </thead>
              <tbody>
                {summary.trending_topics.slice(0, 5).map((t) => (
                  <tr key={t.topic_id} className="border-b border-border/50 last:border-0">
                    <td className="py-2 font-mono text-muted-foreground">#{t.topic_id}</td>
                    <td className="max-w-[220px] truncate py-2">{t.keywords}</td>
                    <td className="py-2 text-right font-mono text-xs text-signal-green">{t.doc_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
              Waiting for topic signals
            </div>
          )}
        </ChartCard>
      </div>
    </div>
  );
}
