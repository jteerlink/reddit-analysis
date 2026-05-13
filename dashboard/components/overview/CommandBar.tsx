"use client";

import { CalendarDays, RadioTower, RefreshCw, Search } from "lucide-react";
import type { SubredditCategory } from "@/lib/types";
import { parentColor } from "@/lib/utils";

interface Props {
  selectedSubreddits: string[];
  selectedParents: string[];
  parentCategories: SubredditCategory[];
  dateRange: [string, string];
  allSubreddits: string[];
  onToggleSubreddit: (subreddit: string) => void;
  onToggleParent: (parentId: string) => void;
  onClearSubreddits: () => void;
  onClearParents: () => void;
  onDateRangeChange: (range: [string, string]) => void;
  onRefresh: () => void;
}

export function CommandBar({
  selectedSubreddits,
  selectedParents,
  parentCategories,
  dateRange,
  allSubreddits,
  onToggleSubreddit,
  onToggleParent,
  onClearSubreddits,
  onClearParents,
  onDateRangeChange,
  onRefresh,
}: Props) {
  const rangeLabel = dateRange[0] && dateRange[1] ? `${dateRange[0]} to ${dateRange[1]}` : "Full range";
  const parentLabel = selectedParents.length
    ? `${selectedParents.length} parent${selectedParents.length === 1 ? "" : "s"}`
    : "All parents";
  const subredditExtraLabel = selectedSubreddits.length ? ` / +${selectedSubreddits.length} subs` : "";

  const parentMap = new Map(parentCategories.map((p) => [p.id, p]));

  return (
    <header className="flex flex-col gap-3 rounded-lg border border-border bg-card/72 px-4 py-3 shadow-[0_18px_60px_rgba(0,0,0,0.24)] backdrop-blur md:flex-row md:items-center md:justify-between">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid size-9 shrink-0 place-items-center rounded-md border border-signal-green/30 bg-signal-green/10 text-signal-green">
          <RadioTower className="size-4" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="command-label">Overview</p>
          <h1 className="truncate text-[1.75rem] font-semibold leading-[1.05] tracking-[-0.015em] text-foreground">Signal Command</h1>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {selectedParents.length > 0 && (
          <div className="flex flex-wrap items-center gap-1">
            {selectedParents.map((parentId) => {
              const cat = parentMap.get(parentId);
              return (
                <button
                  key={parentId}
                  type="button"
                  onClick={() => onToggleParent(parentId)}
                  className="flex h-7 items-center gap-1.5 rounded-full border border-border bg-background/60 pl-1.5 pr-2 text-[11px] text-foreground hover:bg-muted"
                  title="Remove parent filter"
                >
                  <span className="size-2 rounded-full" style={{ background: parentColor(parentId) }} />
                  <span>{cat?.display_name ?? parentId}</span>
                  <span className="text-muted-foreground">×</span>
                </button>
              );
            })}
            <button
              type="button"
              onClick={onClearParents}
              className="text-[10px] text-signal-copper hover:text-foreground"
            >
              Clear
            </button>
          </div>
        )}

        <details className="relative">
          <summary className="flex h-9 cursor-pointer list-none items-center gap-2 rounded-md border border-border bg-background/60 px-3 text-xs text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
            <Search className="size-3.5 text-signal-copper" aria-hidden="true" />
            <span>{parentLabel}{subredditExtraLabel}</span>
          </summary>
          <div className="absolute right-0 z-20 mt-2 w-72 rounded-lg border border-border bg-card p-3 shadow-2xl">
            <div className="mb-2 flex items-center justify-between">
              <p className="command-label">Parents</p>
              <button type="button" onClick={onClearParents} className="text-[11px] text-signal-copper hover:text-foreground">
                Clear
              </button>
            </div>
            <div className="mb-3 max-h-44 space-y-1 overflow-y-auto pr-1">
              {parentCategories.map((parent) => (
                <label key={parent.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground">
                  <input
                    type="checkbox"
                    checked={selectedParents.includes(parent.id)}
                    onChange={() => onToggleParent(parent.id)}
                    className="accent-emerald-400"
                  />
                  <span className="size-2 rounded-full" style={{ background: parentColor(parent.id) }} />
                  <span className="flex-1 truncate">{parent.display_name}</span>
                  <span className="font-mono text-[10px] tabular-nums text-muted-foreground">{parent.volume.toLocaleString()}</span>
                </label>
              ))}
            </div>
            <div className="mb-2 flex items-center justify-between">
              <p className="command-label">Subreddits</p>
              <button type="button" onClick={onClearSubreddits} className="text-[11px] text-signal-copper hover:text-foreground">
                Clear
              </button>
            </div>
            <div className="max-h-44 space-y-1 overflow-y-auto pr-1">
              {allSubreddits.map((subreddit) => (
                <label key={subreddit} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs text-muted-foreground hover:bg-muted hover:text-foreground">
                  <input
                    type="checkbox"
                    checked={selectedSubreddits.includes(subreddit)}
                    onChange={() => onToggleSubreddit(subreddit)}
                    className="accent-emerald-400"
                  />
                  <span className="truncate">{subreddit}</span>
                </label>
              ))}
            </div>
          </div>
        </details>
        <div className="flex min-h-9 flex-wrap items-center gap-2 rounded-md border border-border bg-background/60 px-3 py-1.5 text-xs text-muted-foreground" title={rangeLabel}>
          <CalendarDays className="size-3.5 text-signal-copper" aria-hidden="true" />
          <input
            type="date"
            value={dateRange[0]}
            onChange={(event) => onDateRangeChange([event.target.value, dateRange[1]])}
            className="w-[8.4rem] bg-transparent font-mono text-[11px] text-foreground outline-none"
            aria-label="Start date"
          />
          <span className="text-muted-foreground">to</span>
          <input
            type="date"
            value={dateRange[1]}
            onChange={(event) => onDateRangeChange([dateRange[0], event.target.value])}
            className="w-[8.4rem] bg-transparent font-mono text-[11px] text-foreground outline-none"
            aria-label="End date"
          />
        </div>
        <button onClick={onRefresh} className="grid size-9 place-items-center rounded-md border border-signal-copper/35 bg-signal-copper/10 text-signal-copper transition-colors hover:bg-signal-copper/16" aria-label="Refresh dashboard">
          <RefreshCw className="size-3.5" aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
