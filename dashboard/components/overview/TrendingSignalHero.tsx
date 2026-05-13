"use client";

import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";
import { ChartCard } from "@/components/shared/ChartCard";
import type { TrendingTopic } from "@/lib/types";
import { parentColor } from "@/lib/utils";

function topicHeadline(topic: TrendingTopic): string {
  const llmLabel = topic.label || topic.llm_label;
  if (llmLabel) return llmLabel;
  return topic.keywords.replace(/[[\]"]/g, "").split(",").slice(0, 3).join(", ").trim() || `Topic #${topic.topic_id}`;
}

function keywordSubtitle(topic: TrendingTopic): string {
  return topic.keywords
    .replace(/[[\]"]/g, "")
    .split(/[,\s]+/)
    .filter(Boolean)
    .slice(0, 6)
    .join(" / ");
}

function Sparkline({ values }: { values: number[] }) {
  if (!values || values.length < 2) return null;
  const max = Math.max(...values, 1);
  const min = Math.min(...values);
  const range = Math.max(max - min, 1);
  const w = 64;
  const h = 22;
  const step = w / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - min) / range) * h).toFixed(1)}`)
    .join(" ");
  const last = values[values.length - 1];
  const prev = values[values.length - 2];
  const trendUp = last >= prev;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-5 w-16" aria-hidden="true">
      <polyline
        fill="none"
        stroke={trendUp ? "#31d38f" : "#e26464"}
        strokeWidth={1.4}
        points={points}
      />
    </svg>
  );
}

interface Props {
  topics: TrendingTopic[] | undefined;
}

export function TrendingSignalHero({ topics }: Props) {
  const items = (topics ?? []).slice(0, 5);
  return (
    <ChartCard
      title="Trending signal"
      subtitle="Top topics this week, labelled by the LLM enrichment pipeline."
      action={
        <Link
          href="/topics"
          className="flex items-center gap-1 text-[11px] text-signal-copper hover:text-foreground"
        >
          <Sparkles className="size-3" /> Explore <ArrowRight className="size-3" />
        </Link>
      }
    >
      {items.length ? (
        <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-5">
          {items.map((topic) => {
            const headline = topicHeadline(topic);
            const subtitle = keywordSubtitle(topic);
            const parents = topic.parents ?? [];
            const weeklyCounts = topic.weekly_counts ?? [];
            return (
              <div
                key={topic.topic_id}
                className="flex flex-col gap-2 rounded-lg border border-border bg-background/45 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold leading-tight tracking-[-0.01em] text-foreground line-clamp-2">
                    {headline}
                  </p>
                  <Sparkline values={weeklyCounts} />
                </div>
                {subtitle && (
                  <p className="font-mono text-[10.5px] uppercase tracking-wide text-muted-foreground line-clamp-2">
                    {subtitle}
                  </p>
                )}
                <div className="mt-auto flex flex-wrap items-center gap-1">
                  <span className="rounded border border-signal-green/25 bg-signal-green/10 px-2 py-0.5 font-mono text-[10px] text-signal-green">
                    {topic.doc_count.toLocaleString()} docs
                  </span>
                  {parents.slice(0, 3).map((p) => (
                    <span
                      key={p.parent_id}
                      className="flex items-center gap-1 rounded border border-border bg-card/80 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                      title={`${p.doc_count} docs from ${p.display_name}`}
                    >
                      <span className="size-1.5 rounded-full" style={{ background: parentColor(p.parent_id) }} />
                      {p.display_name}
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="grid h-24 place-items-center text-sm text-muted-foreground">
          Waiting for topic signals
        </div>
      )}
    </ChartCard>
  );
}
