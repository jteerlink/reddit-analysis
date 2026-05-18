"use client";

import useSWR from "swr";
import { useSWRConfig } from "swr";
import { useFilterStore } from "@/lib/store";
import { MetricCard } from "@/components/shared/MetricCard";
import { ActivityFeedStrip } from "@/components/overview/ActivityFeedStrip";
import { CommandBar } from "@/components/overview/CommandBar";
import { PipelineHealthCard } from "@/components/overview/PipelineHealthCard";
import { SignalStreamChart } from "@/components/overview/SignalStreamChart";
import { ParentSummaryPanel } from "@/components/overview/ParentSummaryPanel";
import { TrendingSignalHero } from "@/components/overview/TrendingSignalHero";
import type {
  CollectionSummary,
  ChartSummaryResponse,
  SentimentDaily,
  SentimentSummary,
  SubredditCategoriesResponse,
  VolumeDaily,
} from "@/lib/types";

type PanelState = "ready" | "loading" | "empty" | "error";

const fetcher = async (url: string) => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
};

function buildQuery(subreddits: string[], parents: string[], dateRange: [string, string]) {
  const params = new URLSearchParams();
  subreddits.forEach((s) => params.append("subreddits", s));
  parents.forEach((p) => params.append("parents", p));
  if (dateRange[0]) params.set("start", dateRange[0]);
  if (dateRange[1]) params.set("end", dateRange[1]);
  const query = params.toString();
  return query ? `?${query}` : "";
}

function stateMessage(state: PanelState, messages: Partial<Record<PanelState, string>>) {
  return state === "ready" ? undefined : messages[state];
}

export default function OverviewPage() {
  const { mutate } = useSWRConfig();
  const { subreddits, setSubreddits, parents, setParents, dateRange, setDateRange } = useFilterStore();
  const q = buildQuery(subreddits, parents, dateRange);

  const { data: summary, error: summaryError } = useSWR<CollectionSummary>(`/api/summary${q}`, fetcher);
  const { data: sentimentData, error: sentimentError } = useSWR<SentimentSummary[]>(`/api/sentiment/summary${q}`, fetcher);
  const { data: sentimentDaily } = useSWR<SentimentDaily[]>(`/api/sentiment/daily${q}`, fetcher);
  const { data: volumeData } = useSWR<VolumeDaily[]>(`/api/volume/daily${q}`, fetcher);
  const { data: chartSummary } = useSWR<ChartSummaryResponse>(`/api/analysis/overview-chart-summary${q}`, fetcher);
  const { data: allSubreddits = [] } = useSWR<string[]>("/api/subreddits", fetcher);
  const { data: categories } = useSWR<SubredditCategoriesResponse>("/api/subreddits/categories", fetcher);

  const hasSummary = typeof summary?.total_posts === "number" && typeof summary?.total_comments === "number";
  const summaryInvalid = !!summary && !hasSummary;
  const summaryLoading = !summary && !summaryError;
  const hasScopedFilters = parents.length > 0 || subreddits.length > 0;
  const noMatchMessage = hasScopedFilters ? "No records match the selected community filters." : "No records match the selected date range.";

  const totalPostsState: PanelState = summaryError || summaryInvalid
    ? "error"
    : summaryLoading
      ? "loading"
      : (summary?.total_posts ?? 0) === 0
        ? "empty"
        : "ready";
  const totalCommentsState: PanelState = summaryError || summaryInvalid
    ? "error"
    : summaryLoading
      ? "loading"
      : (summary?.total_comments ?? 0) === 0
        ? "empty"
        : "ready";
  const lastMLState: PanelState = summaryError || summaryInvalid
    ? "error"
    : summaryLoading
      ? "loading"
      : summary?.last_ml_timestamp
        ? "ready"
        : "empty";

  const totalPosts = hasSummary ? summary.total_posts.toLocaleString() : undefined;
  const totalComments = hasSummary ? summary.total_comments.toLocaleString() : undefined;
  const lastML = summary?.last_ml_timestamp?.slice(0, 10);

  const posCount = sentimentData?.find((d) => d.label === "positive")?.count ?? 0;
  const negCount = sentimentData?.find((d) => d.label === "negative")?.count ?? 0;
  const neuCount = sentimentData?.find((d) => d.label === "neutral")?.count ?? 0;
  const total = posCount + negCount + neuCount;
  const sentimentState: PanelState = sentimentError
    ? "error"
    : !sentimentData
      ? "loading"
      : total === 0
        ? "empty"
        : "ready";
  const sentimentMix = total ? `${Math.round((posCount / total) * 100)}% pos` : undefined;
  const topicState: PanelState = summaryError || summaryInvalid
    ? "error"
    : summaryLoading
      ? "loading"
      : summary?.trending_topics?.length
        ? "ready"
        : "empty";
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

      <TrendingSignalHero
        topics={summary?.trending_topics}
        state={topicState}
        message={
          topicState === "loading"
            ? "Checking the active dashboard filters."
            : topicState === "empty"
              ? "Try broadening the selected communities or date range."
              : topicState === "error"
                ? "The summary endpoint did not return usable topic data."
                : undefined
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total posts"
          value={totalPosts}
          sub="indexed signals"
          state={totalPostsState}
          message={stateMessage(totalPostsState, {
            loading: "Checking indexed posts.",
            empty: noMatchMessage,
            error: "Could not load post totals.",
          })}
        />
        <MetricCard
          label="Total comments"
          value={totalComments}
          sub="conversation mass"
          state={totalCommentsState}
          message={stateMessage(totalCommentsState, {
            loading: "Checking comment volume.",
            empty: noMatchMessage,
            error: "Could not load comment totals.",
          })}
        />
        <MetricCard
          label="Last ML run"
          value={lastML}
          sub="model refresh"
          state={lastMLState}
          message={stateMessage(lastMLState, {
            loading: "Checking model freshness.",
            empty: "No model run is available for this view.",
            error: "Could not load model freshness.",
          })}
        />
        <MetricCard
          label="Sentiment mix"
          value={sentimentMix}
          sub="active window"
          state={sentimentState}
          message={stateMessage(sentimentState, {
            loading: "Checking sentiment labels.",
            empty: "No sentiment labels match this view.",
            error: "Could not load sentiment mix.",
          })}
          accent
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(380px,0.75fr)]">
        <SignalStreamChart volumeData={volumeData} sentimentData={sentimentData} sentimentDaily={sentimentDaily} chartSummary={chartSummary} />

        <div className="grid gap-4">
          <PipelineHealthCard />
          <ParentSummaryPanel parents={categories?.parents ?? []} />
        </div>
      </div>

      <ActivityFeedStrip />
    </div>
  );
}
