"use client";

import Link from "next/link";
import { ArrowRight, Layers3 } from "lucide-react";
import { useFilterStore } from "@/lib/store";
import { parentColor } from "@/lib/utils";
import type { SubredditCategory } from "@/lib/types";

interface Props {
  parents: SubredditCategory[];
}

function sentimentChip(mean: number | null | undefined) {
  if (mean === null || mean === undefined) return null;
  const positive = mean >= 0;
  const tone = positive ? "text-signal-green" : "text-signal-red";
  return (
    <span className={`font-mono text-[11px] tabular-nums ${tone}`}>
      {positive ? "+" : ""}
      {mean.toFixed(2)}
    </span>
  );
}

export function ParentSummaryPanel({ parents }: Props) {
  const { setParents } = useFilterStore();
  const ordered = [...parents].sort((a, b) =>
    a.sort_order !== b.sort_order ? a.sort_order - b.sort_order : b.volume - a.volume,
  );

  return (
    <section className="command-panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="command-label">Parents</p>
          <h3 className="mt-1 text-[14px] font-semibold tracking-[-0.012em] text-foreground">
            Community groups
          </h3>
        </div>
        <Layers3 className="size-3.5 text-muted-foreground" aria-hidden="true" />
      </div>

      <div className="mt-3 space-y-1">
        {ordered.length ? (
          ordered.map((parent) => (
            <button
              key={parent.id}
              type="button"
              onClick={() => setParents([parent.id])}
              className="grid w-full grid-cols-[auto_1fr_auto_auto] items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-muted"
            >
              <span
                className="size-2 rounded-full"
                style={{ background: parentColor(parent.id) }}
              />
              <span className="truncate text-foreground">{parent.display_name}</span>
              {sentimentChip(parent.mean_sentiment)}
              <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                {parent.volume.toLocaleString()}
              </span>
            </button>
          ))
        ) : (
          <div className="grid h-24 place-items-center rounded-md border border-border bg-card/40 text-xs text-muted-foreground">
            Waiting for parent categories
          </div>
        )}
      </div>

      <Link
        href="/topics"
        className="mt-4 flex w-full items-center justify-between rounded-md border border-signal-copper/25 bg-signal-copper/8 px-3 py-2 text-xs text-signal-copper transition-colors hover:border-signal-copper/50 hover:bg-signal-copper/12"
      >
        Open subreddit network
        <ArrowRight className="size-3.5" aria-hidden="true" />
      </Link>
    </section>
  );
}
