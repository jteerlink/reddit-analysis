"use client";

import { ArrowRight, Maximize2, Sparkles } from "lucide-react";
import type { Topic } from "@/lib/types";

interface Props {
  topics?: Topic[];
}

const DEFAULT_TOPICS = [
  { topic_id: 1, keywords: "AI regulation", doc_count: 12400, coherence_score: 0.41 },
  { topic_id: 2, keywords: "OpenAI", doc_count: 10100, coherence_score: 0.36 },
  { topic_id: 3, keywords: "Earnings", doc_count: 8700, coherence_score: -0.12 },
  { topic_id: 4, keywords: "Inflation", doc_count: 7200, coherence_score: -0.28 },
  { topic_id: 5, keywords: "Crypto", doc_count: 6800, coherence_score: 0.09 },
];

const NODES = [
  [20, 42, 4, "#7c5cff"], [32, 22, 3, "#31d38f"], [43, 50, 5, "#c8d64a"], [58, 38, 4, "#31d38f"],
  [70, 62, 3, "#7c5cff"], [30, 72, 4, "#31d38f"], [52, 18, 3, "#c07a45"], [75, 28, 4, "#c8d64a"],
  [46, 73, 3, "#7c5cff"], [62, 78, 5, "#31d38f"], [38, 36, 3, "#c07a45"], [54, 55, 2, "#c8d64a"],
];

const CORE_DOTS = [
  [51, 50], [51.5, 52.8], [49.1, 55.5], [45.7, 54.1], [40.7, 55.5], [35, 51.9],
  [35.1, 47.7], [35.6, 43.8], [40.4, 41.1], [44.3, 39.6], [49.6, 43.5], [55.2, 41.5],
  [55, 46.8], [58.9, 51.7], [55.6, 54.8], [52.2, 58.4], [46.4, 60.7], [40.9, 56.1],
  [35.3, 55.6], [31.4, 49.3], [33.4, 44.1], [34.9, 37.6], [43, 37.2], [48.8, 38.7],
  [54.3, 42.6], [60.4, 48.1],
];

function formatCount(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return value.toLocaleString();
}

function topicName(keywords: string) {
  return keywords.replace(/[[\]"]/g, "").split(",")[0].trim() || keywords.slice(0, 18);
}

export function TopicExplorerPanel({ topics }: Props) {
  const rows = (topics?.slice(0, 5) ?? DEFAULT_TOPICS).map((topic, index) => ({
    ...topic,
    coherence_score: topic.coherence_score ?? [0.41, 0.36, -0.12, -0.28, 0.09][index],
  }));

  return (
    <section className="command-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="command-label">Topic Explorer</p>
          <h3 className="mt-1 text-sm font-semibold text-foreground">Signal clusters</h3>
        </div>
        <div className="flex items-center gap-2 text-muted-foreground">
          <Sparkles className="size-3.5" aria-hidden="true" />
          <Maximize2 className="size-3.5" aria-hidden="true" />
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-[0.95fr_1.05fr]">
        <div className="relative aspect-square min-h-44 rounded-lg border border-white/8 bg-black/20 signal-grid">
          <svg className="absolute inset-3 h-[calc(100%-1.5rem)] w-[calc(100%-1.5rem)]" viewBox="0 0 100 100" aria-label="Topic network cluster">
            <path d="M20 42 L32 22 L52 18 L75 28 L58 38 L43 50 L30 72 L46 73 L62 78 L70 62 L54 55 L38 36 Z" fill="none" stroke="rgba(255,255,255,0.14)" strokeWidth="0.8" />
            <path d="M43 50 L58 38 L75 28 M43 50 L62 78 M38 36 L54 55 L70 62" fill="none" stroke="rgba(49,211,143,0.22)" strokeWidth="0.8" />
            {NODES.map(([cx, cy, r, fill]) => (
              <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={r} fill={fill as string} opacity="0.88" />
            ))}
            {CORE_DOTS.map(([cx, cy], index) => (
              <circle key={index} cx={cx} cy={cy} r="1.25" fill="#d7d856" opacity="0.92" />
            ))}
          </svg>
        </div>

        <div className="min-w-0">
          <div className="mb-2 flex items-center justify-between font-mono text-[10px] text-muted-foreground">
            <span>Top topics</span>
            <span>delta</span>
          </div>
          <div className="space-y-2">
            {rows.map((topic, index) => {
              const score = topic.coherence_score ?? 0;
              return (
                <div key={topic.topic_id} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 text-xs">
                  <span className="truncate text-foreground">{topicName(topic.keywords)}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">{formatCount(topic.doc_count)}</span>
                  <span className={`font-mono text-[11px] ${score >= 0 ? "text-signal-green" : "text-signal-red"}`}>
                    {score >= 0 ? "+" : ""}{score.toFixed(2)}
                  </span>
                  {index < rows.length - 1 && <div className="col-span-3 h-px bg-border" />}
                </div>
              );
            })}
          </div>
          <button className="mt-4 flex w-full items-center justify-between rounded-md border border-signal-copper/25 bg-signal-copper/8 px-3 py-2 text-xs text-signal-copper transition-colors hover:border-signal-copper/50 hover:bg-signal-copper/12">
            Explore all topics
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      </div>
    </section>
  );
}
