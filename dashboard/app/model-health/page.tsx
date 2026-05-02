"use client";

import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { ChartCard } from "@/components/shared/ChartCard";
import { ConfidenceHistogram } from "@/components/charts/ConfidenceHistogram";
import { VaderAgreementBar } from "@/components/charts/VaderAgreementBar";
import { Skeleton } from "@/components/ui/skeleton";
import type { Post, VaderAgreement } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function ModelHealthPage() {
  const { data: posts } = useSWR<Post[]>("/api/posts/search?limit=500", fetcher);
  const { data: vader } = useSWR<VaderAgreement[]>("/api/model/vader-agreement", fetcher);

  const meanConf = posts?.length
    ? (posts.reduce((s, p) => s + p.confidence, 0) / posts.length).toFixed(3)
    : "—";
  const highConf = posts?.length
    ? `${Math.round((posts.filter((p) => p.confidence >= 0.75).length / posts.length) * 100)}%`
    : "—";
  const avgAgreement = vader?.length
    ? `${Math.round((vader.reduce((s, v) => s + v.agreement_rate, 0) / vader.length) * 100)}%`
    : "—";

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Diagnostics" title="Model health" subtitle="Prediction confidence and VADER agreement metrics." />

      <div className="flex gap-4 flex-wrap">
        <MetricCard label="Mean confidence" value={meanConf} />
        <MetricCard label="≥ 0.75 confidence" value={highConf} accent />
        <MetricCard label="Avg VADER agreement" value={avgAgreement} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Confidence distribution" subtitle="0.75 threshold shown in amber">
          {posts ? (
            <ConfidenceHistogram data={posts} />
          ) : (
            <Skeleton className="h-48 w-full" />
          )}
        </ChartCard>

        <ChartCard title="VADER agreement by subreddit">
          {vader ? (
            <VaderAgreementBar data={vader} />
          ) : (
            <Skeleton className="h-48 w-full" />
          )}
        </ChartCard>
      </div>
    </div>
  );
}
