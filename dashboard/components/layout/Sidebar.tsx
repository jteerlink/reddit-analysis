"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import useSWR from "swr";
import { useFilterStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/overview", label: "Overview" },
  { href: "/sentiment", label: "Sentiment Trends" },
  { href: "/topics", label: "Topic Explorer" },
  { href: "/deep-dive", label: "Deep Dive" },
  { href: "/model-health", label: "Model Health" },
  { href: "/pipeline", label: "Pipeline" },
];

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export function Sidebar() {
  const pathname = usePathname();
  const { subreddits, setSubreddits, dateRange, setDateRange } = useFilterStore();

  const { data: allSubreddits = [] } = useSWR<string[]>("/api/subreddits", fetcher);
  const { data: range } = useSWR<{ start: string; end: string }>("/api/date-range", fetcher);

  useEffect(() => {
    if (range && !dateRange[0]) {
      setDateRange([range.start, range.end]);
    }
  }, [range, dateRange, setDateRange]);

  const toggleSubreddit = (s: string) => {
    setSubreddits(
      subreddits.includes(s) ? subreddits.filter((x) => x !== s) : [...subreddits, s]
    );
  };

  return (
    <aside className="flex h-full w-60 flex-col shrink-0 border-r border-border bg-card overflow-y-auto">
      <div className="px-4 py-5 border-b border-border">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Analytics</p>
        <h1 className="text-base font-semibold text-foreground mt-0.5">Reddit Analyzer</h1>
        <p className="text-xs text-muted-foreground">Sentiment & topic intelligence</p>
      </div>

      <nav className="flex flex-col gap-0.5 px-2 py-3">
        {TABS.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "rounded-md px-3 py-2 text-sm transition-colors",
              pathname === tab.href
                ? "bg-primary text-primary-foreground font-medium"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      <div className="border-t border-border px-4 py-4 flex-1">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
          Subreddits
        </p>
        <div className="flex flex-col gap-1 max-h-64 overflow-y-auto">
          {allSubreddits.map((s) => (
            <label key={s} className="flex items-center gap-2 cursor-pointer text-xs text-muted-foreground hover:text-foreground">
              <input
                type="checkbox"
                checked={subreddits.includes(s)}
                onChange={() => toggleSubreddit(s)}
                className="accent-amber-500"
              />
              {s}
            </label>
          ))}
        </div>

        {range && (
          <div className="mt-4">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground mb-1">
              Date range
            </p>
            <div className="flex flex-col gap-1">
              <input
                type="date"
                value={dateRange[0]}
                min={range.start}
                max={range.end}
                onChange={(e) => setDateRange([e.target.value, dateRange[1]])}
                className="w-full rounded border border-input bg-background px-2 py-1 text-xs text-foreground"
              />
              <input
                type="date"
                value={dateRange[1]}
                min={range.start}
                max={range.end}
                onChange={(e) => setDateRange([dateRange[0], e.target.value])}
                className="w-full rounded border border-input bg-background px-2 py-1 text-xs text-foreground"
              />
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
