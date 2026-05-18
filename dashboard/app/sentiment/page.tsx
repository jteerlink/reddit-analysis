"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { useFilterStore } from "@/lib/store";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { SentimentLineChart } from "@/components/charts/SentimentLineChart";
import { ForecastAreaChart } from "@/components/charts/ForecastAreaChart";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChangePoint, Forecast, SentimentDaily, SubredditCategoriesResponse } from "@/lib/types";

type MAMode = "none" | "7d" | "30d" | "both";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const SENTIMENT_CHART_START_DATE = "2026-04-01";

function buildQuery(subreddits: string[], parents: string[]) {
  if (!subreddits.length && !parents.length) return "";
  const params = new URLSearchParams();
  subreddits.forEach((s) => params.append("subreddits", s));
  parents.forEach((p) => params.append("parents", p));
  return `?${params.toString()}`;
}

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

export default function SentimentPage() {
  const { subreddits, parents, setParents } = useFilterStore();
  const { data: categories } = useSWR<SubredditCategoriesResponse>(
    "/api/subreddits/categories?days=30",
    fetcher,
  );
  const hasInitializedRef = useRef(false);

  useEffect(() => {
    if (hasInitializedRef.current) return;
    if (!categories?.parents?.length) return;
    if (parents.length > 0) {
      hasInitializedRef.current = true;
      return;
    }
    const top3 = [...categories.parents]
      .sort((a, b) => b.volume - a.volume)
      .slice(0, 3)
      .map((p) => p.id);
    if (top3.length) {
      setParents(top3);
    }
    hasInitializedRef.current = true;
  }, [categories, parents.length, setParents]);

  const q = buildQuery(subreddits, parents);
  const seriesLabels = buildSeriesLabels(categories, parents, subreddits);
  const [maMode, setMaMode] = useState<MAMode>("none");

  const { data: daily } = useSWR<SentimentDaily[]>(`/api/sentiment/daily${q}`, fetcher);
  const { data: changePoints } = useSWR<ChangePoint[]>(`/api/sentiment/change-points${q}`, fetcher);
  const { data: forecast } = useSWR<Forecast[]>(`/api/sentiment/forecast${q}`, fetcher);
  const chartDaily = daily?.filter((row) => row.date >= SENTIMENT_CHART_START_DATE);
  const chartChangePoints = changePoints?.filter((row) => row.date >= SENTIMENT_CHART_START_DATE);
  const chartForecast = forecast?.filter((row) => row.date >= SENTIMENT_CHART_START_DATE);

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Sentiment" title="Sentiment trends" subtitle="Daily mean sentiment with optional moving averages and 14-day forecast." />

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
        {chartDaily && chartChangePoints ? (
          <SentimentLineChart data={chartDaily} changePoints={chartChangePoints} maMode={maMode} seriesLabels={seriesLabels} />
        ) : (
          <Skeleton className="h-[420px] w-full" />
        )}
      </ChartCard>

      <ChartCard title="14-day forecast" subtitle="Prophet forecast with 95% confidence band">
        {chartForecast ? (
          <ForecastAreaChart data={chartForecast} seriesLabels={seriesLabels} actualData={chartDaily} />
        ) : (
          <Skeleton className="h-[420px] w-full" />
        )}
      </ChartCard>
    </div>
  );
}
