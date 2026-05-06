"use client";

import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { Skeleton } from "@/components/ui/skeleton";
import type { EmbeddingMapResponse } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const SENTIMENT_CLASS: Record<string, string> = {
  positive: "bg-emerald-400",
  neutral: "bg-slate-300",
  negative: "bg-red-400",
};

export default function EmbeddingMapPage() {
  const { data } = useSWR<EmbeddingMapResponse>("/api/analysis/embedding-map?limit=1200", fetcher);
  const points = data?.items ?? [];
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs, -1);
  const maxX = Math.max(...xs, 1);
  const minY = Math.min(...ys, -1);
  const maxY = Math.max(...ys, 1);

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Semantic Space"
        title="Embedding map"
        subtitle="Projected MiniLM conversation embeddings by cluster and sentiment."
      />

      <ChartCard title="Conversation map" subtitle={data?.provenance?.algorithm ?? "embedding projection"}>
        {data ? (
          <>
            {data.state !== "ready" && (
              <div className="mb-3 rounded-md border border-signal-yellow/25 bg-signal-yellow/10 px-3 py-2 text-xs text-signal-yellow">
                {data.provenance?.detail ?? data.state.replace("_", " ")}
              </div>
            )}
            <div className="relative h-[620px] overflow-hidden rounded-md border border-border bg-background">
              {points.map((point) => {
                const left = ((point.x - minX) / Math.max(maxX - minX, 0.001)) * 100;
                const top = 100 - ((point.y - minY) / Math.max(maxY - minY, 0.001)) * 100;
                return (
                  <div
                    key={point.id}
                    title={`${point.subreddit ?? "unknown"} / topic ${point.topic_id ?? point.cluster_id}: ${point.preview ?? ""}`}
                    className={`absolute size-2 rounded-full opacity-75 ring-1 ring-black/30 ${SENTIMENT_CLASS[point.sentiment ?? ""] ?? "bg-signal-copper"}`}
                    style={{ left: `${left}%`, top: `${top}%` }}
                  />
                );
              })}
              {!points.length && (
                <div className="grid h-full place-items-center text-sm text-muted-foreground">
                  Run the embedding map backfill to populate projected conversations
                </div>
              )}
            </div>
          </>
        ) : (
          <Skeleton className="h-[620px] w-full" />
        )}
      </ChartCard>
    </div>
  );
}
