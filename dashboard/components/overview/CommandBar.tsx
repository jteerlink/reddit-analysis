"use client";

import { CalendarDays, RadioTower, RefreshCw, Search } from "lucide-react";

interface Props {
  selectedSubreddits: string[];
  dateRange: [string, string];
}

export function CommandBar({ selectedSubreddits, dateRange }: Props) {
  const subredditLabel = selectedSubreddits.length ? `${selectedSubreddits.length} subreddits` : "All subreddits";
  const rangeLabel = dateRange[0] && dateRange[1] ? `${dateRange[0]} to ${dateRange[1]}` : "Full range";

  return (
    <header className="flex flex-col gap-3 rounded-lg border border-border bg-card/72 px-4 py-3 shadow-[0_18px_60px_rgba(0,0,0,0.24)] backdrop-blur md:flex-row md:items-center md:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-md border border-signal-green/30 bg-signal-green/10 text-signal-green">
          <RadioTower className="size-4" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="command-label">Overview</p>
          <h1 className="truncate text-lg font-semibold text-foreground">Signal Command</h1>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex h-9 items-center gap-2 rounded-md border border-border bg-background/60 px-3 text-xs text-muted-foreground">
          <Search className="size-3.5 text-signal-copper" aria-hidden="true" />
          <span>{subredditLabel}</span>
        </div>
        <div className="flex h-9 items-center gap-2 rounded-md border border-border bg-background/60 px-3 text-xs text-muted-foreground">
          <CalendarDays className="size-3.5 text-signal-copper" aria-hidden="true" />
          <span>{rangeLabel}</span>
        </div>
        <button className="grid size-9 place-items-center rounded-md border border-signal-copper/35 bg-signal-copper/10 text-signal-copper transition-colors hover:bg-signal-copper/16" aria-label="Refresh dashboard">
          <RefreshCw className="size-3.5" aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
