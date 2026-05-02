"use client";

import useSWR from "swr";
import { useFilterStore } from "@/lib/store";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { ChartCard } from "@/components/shared/ChartCard";
import { VolumeBarChart } from "@/components/charts/VolumeBarChart";
import { SentimentDonut } from "@/components/charts/SentimentDonut";
import { Skeleton } from "@/components/ui/skeleton";
import type { CollectionSummary, SentimentSummary, VolumeDaily } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function buildQuery(subreddits: string[]) {
  if (!subreddits.length) return "";
  return "?" + subreddits.map((s) => `subreddits=${encodeURIComponent(s)}`).join("&");
}

export default function OverviewPage() {
  const { subreddits } = useFilterStore();
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
    : "—";

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Overview" title="Collection summary" subtitle="Aggregated stats across selected subreddits and date range." />

      <div className="flex gap-4 flex-wrap">
        <MetricCard label="Total posts" value={totalPosts} />
        <MetricCard label="Total comments" value={totalComments} />
        <MetricCard label="Last ML run" value={lastML} />
        <MetricCard label="Sentiment mix" value={sentimentMix} accent />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Daily volume" subtitle="Posts + comments per subreddit">
          {volumeData ? (
            <VolumeBarChart data={volumeData} />
          ) : (
            <Skeleton className="h-52 w-full" />
          )}
        </ChartCard>

        <ChartCard title="Sentiment distribution">
          {sentimentData ? (
            <SentimentDonut data={sentimentData} />
          ) : (
            <Skeleton className="h-52 w-full" />
          )}
        </ChartCard>
      </div>

      {summary?.trending_topics?.length ? (
        <ChartCard title="Trending topics" subtitle="Top topics by doc count in the most recent week">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-border">
                <th className="pb-2 font-medium">Topic</th>
                <th className="pb-2 font-medium">Keywords</th>
                <th className="pb-2 font-medium text-right">Docs</th>
              </tr>
            </thead>
            <tbody>
              {summary.trending_topics.map((t) => (
                <tr key={t.topic_id} className="border-b border-border/50 last:border-0">
                  <td className="py-2 text-muted-foreground">#{t.topic_id}</td>
                  <td className="py-2">{t.keywords}</td>
                  <td className="py-2 text-right tabular-nums">{t.doc_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ChartCard>
      ) : null}
    </div>
  );
}
