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

function buildQuery(subreddits: string[], parents: string[]) {
  if (!subreddits.length && !parents.length) return "";
  const params = new URLSearchParams();
  subreddits.forEach((s) => params.append("subreddits", s));
  parents.forEach((p) => params.append("parents", p));
  return `?${params.toString()}`;
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
  const [maMode, setMaMode] = useState<MAMode>("none");

  const { data: daily } = useSWR<SentimentDaily[]>(`/api/sentiment/daily${q}`, fetcher);
  const { data: changePoints } = useSWR<ChangePoint[]>(`/api/sentiment/change-points${q}`, fetcher);
  const { data: forecast } = useSWR<Forecast[]>(`/api/sentiment/forecast${q}`, fetcher);

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
        {daily && changePoints ? (
          <SentimentLineChart data={daily} changePoints={changePoints} maMode={maMode} />
        ) : (
          <Skeleton className="h-64 w-full" />
        )}
      </ChartCard>

      <ChartCard title="14-day forecast" subtitle="Prophet forecast with 95% confidence band">
        {forecast ? (
          <ForecastAreaChart data={forecast} />
        ) : (
          <Skeleton className="h-52 w-full" />
        )}
      </ChartCard>
    </div>
  );
}
