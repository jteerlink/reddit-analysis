"use client";

import { useState } from "react";
import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { TopicBarChart } from "@/components/charts/TopicBarChart";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { Topic, TopicOverTime } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function TagCloud({ keywords }: { keywords: string }) {
  const words = keywords.replace(/[[\]"]/g, "").split(/[,\s]+/).filter(Boolean);
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {words.map((w, i) => (
        <span key={i} className="rounded px-2 py-0.5 text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20">
          {w}
        </span>
      ))}
    </div>
  );
}

export default function TopicsPage() {
  const { data: topics } = useSWR<Topic[]>("/api/topics", fetcher);
  const { data: emerging } = useSWR<Topic[]>("/api/topics/emerging", fetcher);
  const [selected, setSelected] = useState<number | null>(null);

  const emergingIds = new Set((emerging ?? []).map((t) => t.topic_id));

  const selectedTopic = topics?.find((t) => t.topic_id === selected);
  const { data: overTime } = useSWR<TopicOverTime[]>(
    selected !== null ? `/api/topics/${selected}/over-time` : null,
    fetcher
  );

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Topics" title="Topic explorer" subtitle="Browse discovered topics and inspect weekly volume." />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ChartCard title="Topics" subtitle="Ordered by document count">
          <div className="flex flex-col gap-1 max-h-96 overflow-y-auto pr-1">
            {topics ? topics.map((t) => (
              <button
                key={t.topic_id}
                onClick={() => setSelected(t.topic_id)}
                className={`text-left rounded px-3 py-2 text-sm transition-colors flex items-center justify-between gap-2 ${selected === t.topic_id ? "bg-amber-500/10 text-amber-400" : "hover:bg-muted text-muted-foreground hover:text-foreground"}`}
              >
                <span className="truncate">{t.keywords.slice(0, 40)}</span>
                <span className="flex items-center gap-1 shrink-0">
                  {emergingIds.has(t.topic_id) && <Badge variant="secondary" className="text-[9px] h-4">new</Badge>}
                  <span className="tabular-nums text-xs">{t.doc_count}</span>
                </span>
              </button>
            )) : <Skeleton className="h-40 w-full" />}
          </div>
        </ChartCard>

        <div className="lg:col-span-2 space-y-4">
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
            <div className="flex items-center justify-center h-52 text-sm text-muted-foreground border border-border rounded-xl">
              Select a topic to see details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
