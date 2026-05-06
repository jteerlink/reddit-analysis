"use client";

import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { ChartCard } from "@/components/shared/ChartCard";
import { ConfidenceHistogram } from "@/components/charts/ConfidenceHistogram";
import { VaderAgreementBar } from "@/components/charts/VaderAgreementBar";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConfidenceBySubreddit, ConfidenceBySubredditResponse, LowConfidenceExample, LowConfidenceResponse, Post, VaderAgreement, VaderDisagreement, VaderDisagreementResponse } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function ModelHealthPage() {
  const { data: posts } = useSWR<Post[]>("/api/posts/search?limit=500", fetcher);
  const { data: vader } = useSWR<VaderAgreement[]>("/api/model/vader-agreement", fetcher);
  const { data: lowConfidence } = useSWR<LowConfidenceResponse>("/api/model/low-confidence?limit=10", fetcher);
  const { data: disagreements } = useSWR<VaderDisagreementResponse>("/api/model/vader-disagreements?limit=10", fetcher);
  const { data: confidenceBySubreddit } = useSWR<ConfidenceBySubredditResponse>("/api/model/confidence-by-subreddit", fetcher);

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

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <ChartCard title="Low-confidence examples" subtitle="Lowest classifier confidence">
          <StateNotice state={lowConfidence?.state} detail={lowConfidence?.provenance?.detail} />
          <ExampleTable rows={lowConfidence?.items ?? []} />
        </ChartCard>

        <ChartCard title="VADER disagreements" subtitle="Model and lexicon labels differ">
          <StateNotice state={disagreements?.state} detail={disagreements?.provenance?.detail} />
          <ExampleTable rows={disagreements?.items ?? []} showVader />
        </ChartCard>

        <ChartCard title="Confidence by subreddit" subtitle="Lowest average first">
          <StateNotice state={confidenceBySubreddit?.state} detail={confidenceBySubreddit?.provenance?.detail} />
          <div className="space-y-2">
            {(confidenceBySubreddit?.items ?? []).slice(0, 8).map((row) => (
              <div key={row.subreddit} className="grid grid-cols-[1fr_auto] gap-3 rounded-md border border-border/60 px-3 py-2 text-sm">
                <span className="truncate text-muted-foreground">{row.subreddit}</span>
                <span className="font-mono tabular-nums">{row.mean_confidence.toFixed(2)}</span>
                <span className="text-xs text-muted-foreground">{row.total.toLocaleString()} rows</span>
                <span className="text-right text-xs text-muted-foreground">{row.low_confidence_count.toLocaleString()} low</span>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>
    </div>
  );
}

function StateNotice({ state, detail }: { state?: string; detail?: string | null }) {
  if (!state || state === "ready") return null;
  return (
    <div className="mb-3 rounded-md border border-signal-yellow/25 bg-signal-yellow/10 px-3 py-2 text-xs text-signal-yellow">
      {detail ?? state.replace("_", " ")}
    </div>
  );
}

function ExampleTable({ rows, showVader = false }: { rows: Array<LowConfidenceExample | VaderDisagreement>; showVader?: boolean }) {
  if (!rows.length) {
    return <div className="grid h-36 place-items-center text-sm text-muted-foreground">No examples</div>;
  }
  return (
    <div className="max-h-80 overflow-y-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="pb-2 font-medium">Subreddit</th>
            <th className="pb-2 font-medium">Label</th>
            {showVader && <th className="pb-2 font-medium">VADER</th>}
            <th className="pb-2 font-medium">Conf.</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-border/50 last:border-0 align-top">
              <td className="py-2 text-muted-foreground">{row.subreddit}</td>
              <td className="py-2">{row.label}</td>
              {showVader && <td className="py-2">{(row as VaderDisagreement).vader_label}</td>}
              <td className="py-2 font-mono tabular-nums">{row.confidence.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 space-y-2">
        {rows.slice(0, 3).map((row) => (
          <p key={`${row.id}-preview`} className="line-clamp-2 text-xs text-muted-foreground">{row.text_preview}</p>
        ))}
      </div>
    </div>
  );
}
