"use client";

import useSWR from "swr";
import { useSWRConfig } from "swr";
import { useFilterStore } from "@/lib/store";
import { MetricCard } from "@/components/shared/MetricCard";
import { ActivityFeedStrip } from "@/components/overview/ActivityFeedStrip";
import { CommandBar } from "@/components/overview/CommandBar";
import { PipelineHealthCard } from "@/components/overview/PipelineHealthCard";
import { SignalStreamChart } from "@/components/overview/SignalStreamChart";
import { TopicExplorerPanel } from "@/components/overview/TopicExplorerPanel";
import { TrendingSignalHero } from "@/components/overview/TrendingSignalHero";
import type {
  CollectionSummary,
  SentimentDaily,
  SentimentSummary,
  SubredditCategoriesResponse,
  VolumeDaily,
} from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function buildQuery(subreddits: string[], parents: string[], dateRange: [string, string]) {
  const params = new URLSearchParams();
  subreddits.forEach((s) => params.append("subreddits", s));
  parents.forEach((p) => params.append("parents", p));
  if (dateRange[0]) params.set("start", dateRange[0]);
  if (dateRange[1]) params.set("end", dateRange[1]);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export default function OverviewPage() {
  const { mutate } = useSWRConfig();
  const { subreddits, setSubreddits, parents, setParents, dateRange, setDateRange } = useFilterStore();
  const q = buildQuery(subreddits, parents, dateRange);

  const { data: summary } = useSWR<CollectionSummary>(`/api/summary${q}`, fetcher);
  const { data: sentimentData } = useSWR<SentimentSummary[]>(`/api/sentiment/summary${q}`, fetcher);
  const { data: sentimentDaily } = useSWR<SentimentDaily[]>(`/api/sentiment/daily${q}`, fetcher);
  const { data: volumeData } = useSWR<VolumeDaily[]>(`/api/volume/daily${q}`, fetcher);
  const { data: allSubreddits = [] } = useSWR<string[]>("/api/subreddits", fetcher);
  const { data: categories } = useSWR<SubredditCategoriesResponse>("/api/subreddits/categories", fetcher);

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
  const toggleSubreddit = (subreddit: string) => {
    setSubreddits(
      subreddits.includes(subreddit)
        ? subreddits.filter((s) => s !== subreddit)
        : [...subreddits, subreddit],
    );
  };
  const toggleParent = (parentId: string) => {
    setParents(
      parents.includes(parentId)
        ? parents.filter((p) => p !== parentId)
        : [...parents, parentId],
    );
  };
  const refreshOverview = () => {
    mutate((key) => typeof key === "string" && key.startsWith("/api/"));
  };

  return (
    <div className="mx-auto flex max-w-[1680px] flex-col gap-4">
      <CommandBar
        selectedSubreddits={subreddits}
        selectedParents={parents}
        parentCategories={categories?.parents ?? []}
        dateRange={dateRange}
        allSubreddits={allSubreddits}
        onToggleSubreddit={toggleSubreddit}
        onToggleParent={toggleParent}
        onClearSubreddits={() => setSubreddits([])}
        onClearParents={() => setParents([])}
        onDateRangeChange={setDateRange}
        onRefresh={refreshOverview}
      />

      <TrendingSignalHero topics={summary?.trending_topics} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Total posts" value={totalPosts} sub="indexed signals" />
        <MetricCard label="Total comments" value={totalComments} sub="conversation mass" />
        <MetricCard label="Last ML run" value={lastML} sub="model refresh" />
        <MetricCard label="Sentiment mix" value={sentimentMix} sub="active window" accent />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(380px,0.75fr)]">
        <SignalStreamChart volumeData={volumeData} sentimentData={sentimentData} sentimentDaily={sentimentDaily} />

        <div className="grid gap-4">
          <PipelineHealthCard />
          <TopicExplorerPanel topics={summary?.trending_topics} />
        </div>
      </div>

      <ActivityFeedStrip />
    </div>
  );
}
