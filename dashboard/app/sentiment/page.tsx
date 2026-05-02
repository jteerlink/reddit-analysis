"use client";

import { useState } from "react";
import useSWR from "swr";
import { useFilterStore } from "@/lib/store";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { SentimentLineChart } from "@/components/charts/SentimentLineChart";
import { ForecastAreaChart } from "@/components/charts/ForecastAreaChart";
import { Skeleton } from "@/components/ui/skeleton";
import type { SentimentDaily, ChangePoint, Forecast } from "@/lib/types";

type MAMode = "none" | "7d" | "30d" | "both";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function buildQuery(subreddits: string[]) {
  if (!subreddits.length) return "";
  return "?" + subreddits.map((s) => `subreddits=${encodeURIComponent(s)}`).join("&");
}

export default function SentimentPage() {
  const { subreddits } = useFilterStore();
  const q = buildQuery(subreddits);
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
