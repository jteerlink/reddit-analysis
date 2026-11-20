"use client";

import { useState } from "react";
import useSWR from "swr";
import { buildFilterQuery, useFilterStore } from "@/lib/store";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { SentimentLineChart } from "@/components/charts/SentimentLineChart";
import { ForecastAreaChart } from "@/components/charts/ForecastAreaChart";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChangePoint, Forecast, SentimentDaily, SubredditCategoriesResponse } from "@/lib/types";

type MAMode = "none" | "7d" | "30d" | "both";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
function buildSeriesLabels(
  categories: SubredditCategoriesResponse | undefined,
  parents: string[],
  subreddits: string[],
) {
  const labels: Record<string, string> = {};
  const selectedParents = new Set(parents);
  const selectedSubreddits = new Set(subreddits);
  const shouldGroupByParent = parents.length > 0 || subreddits.length === 0;

  for (const parent of categories?.parents ?? []) {
    if (shouldGroupByParent && (!selectedParents.size || selectedParents.has(parent.id))) {
      for (const subreddit of parent.subreddits) {
        labels[subreddit] = parent.display_name;
      }
    }
  }

  for (const subreddit of subreddits) {
    if (!labels[subreddit] || (!parents.length && selectedSubreddits.has(subreddit))) {
      labels[subreddit] = subreddit;
    }
  }

  return labels;
}

function buildCommunityQuery(subreddits: string[], parents: string[]) {
  const params = new URLSearchParams();
  subreddits.forEach((subreddit) => params.append("subreddits", subreddit));
  parents.forEach((parent) => params.append("parents", parent));
  const query = params.toString();
  return query ? `?${query}` : "";
}

export default function SentimentPage() {
  const { subreddits, parents, dateRange } = useFilterStore();
  const { data: categories } = useSWR<SubredditCategoriesResponse>(
    "/api/subreddits/categories?days=30",
    fetcher,
  );
  const q = buildFilterQuery(subreddits, parents, dateRange);
  // Forecast runs carry their own training-through and future horizon. Keep the
  // historical research window from clipping the future portion of the run.
  const forecastQuery = buildCommunityQuery(subreddits, parents);
  const seriesLabels = buildSeriesLabels(categories, parents, subreddits);
  const [maMode, setMaMode] = useState<MAMode>("none");

  const { data: daily } = useSWR<SentimentDaily[]>(`/api/sentiment/daily${q}`, fetcher);
  const { data: changePoints } = useSWR<ChangePoint[]>(`/api/sentiment/change-points${q}`, fetcher);
  const { data: forecast } = useSWR<Forecast[]>(`/api/sentiment/forecast${forecastQuery}`, fetcher);
  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Sentiment" title="Sentiment trends" subtitle="Daily mean sentiment with optional moving averages and the latest forecast horizon." />

      <ChartCard
        title="Daily sentiment"
        subtitle="Change points shown as dashed vertical lines"
        action={
          <div className="flex gap-1 text-xs">
            {(["none", "7d", "30d", "both"] as MAMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMaMode(m)}
                className={`px-2 py-1 rounded transition-colors ${maMode === m ? "bg-amber-500 text-black font-medium" : "text-muted-foreground hover:text-foreground"}`}
              >
                {m}
              </button>
            ))}
          </div>
        }
      >
        {daily && changePoints ? (
          <SentimentLineChart data={daily} changePoints={changePoints} maMode={maMode} seriesLabels={seriesLabels} />
        ) : (
          <Skeleton className="h-[420px] w-full" />
        )}
      </ChartCard>

      <ChartCard title="Latest forecast" subtitle="Latest run by community; future horizon begins after training-through. The configured interval is shown in the chart metadata.">
        {forecast ? (
          <ForecastAreaChart data={forecast} seriesLabels={seriesLabels} actualData={daily} />
        ) : (
          <Skeleton className="h-[420px] w-full" />
        )}
      </ChartCard>
    </div>
  );
}
