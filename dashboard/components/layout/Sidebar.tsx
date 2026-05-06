"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import useSWR from "swr";
import { Activity, BarChart3, BrainCircuit, FileText, Gauge, GitBranch, Layers3, Network, RadioTower, Zap } from "lucide-react";
import { useFilterStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/overview", label: "Overview", icon: Gauge },
  { href: "/sentiment", label: "Sentiment Trends", icon: Activity },
  { href: "/topics", label: "Topic Explorer", icon: Layers3 },
  { href: "/deep-dive", label: "Deep Dive", icon: BarChart3 },
  { href: "/embedding-map", label: "Embedding Map", icon: Network },
  { href: "/events", label: "Events", icon: Zap },
  { href: "/briefs", label: "Briefs", icon: FileText },
  { href: "/model-health", label: "Model Health", icon: BrainCircuit },
  { href: "/pipeline", label: "Pipeline", icon: GitBranch },
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
    <aside className="hidden h-full w-64 shrink-0 flex-col overflow-y-auto border-r border-sidebar-border bg-sidebar/88 backdrop-blur md:flex">
      <div className="border-b border-sidebar-border px-4 py-5">
        <div className="flex items-center gap-3">
          <div className="grid size-9 place-items-center rounded-lg border border-signal-green/30 bg-signal-green/10 text-signal-green">
            <RadioTower className="size-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="command-label">Analytics</p>
            <h1 className="mt-0.5 truncate text-base font-semibold text-sidebar-foreground">Signal Command</h1>
          </div>
        </div>
        <p className="mt-3 text-xs leading-5 text-muted-foreground">Subreddit intelligence, live from the stream.</p>
      </div>

      <nav className="flex flex-col gap-0.5 px-2 py-3">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
              pathname === tab.href
                ? "bg-signal-green/12 text-signal-green ring-1 ring-signal-green/22"
                : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground"
            )}
          >
            <Icon className="size-4" aria-hidden="true" />
            {tab.label}
          </Link>
          );
        })}
      </nav>

      <div className="flex-1 border-t border-sidebar-border px-4 py-4">
        <p className="command-label mb-2">
          Subreddits
        </p>
        <div className="flex flex-col gap-1 max-h-64 overflow-y-auto">
          {allSubreddits.map((s) => (
            <label key={s} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground">
              <input
                type="checkbox"
                checked={subreddits.includes(s)}
                onChange={() => toggleSubreddit(s)}
                className="accent-emerald-400"
              />
              {s}
            </label>
          ))}
        </div>

        {range && (
          <div className="mt-4">
            <p className="command-label mb-2">
              Date range
            </p>
            <div className="flex flex-col gap-1">
              <input
                type="date"
                value={dateRange[0]}
                min={range.start}
                max={range.end}
                onChange={(e) => setDateRange([e.target.value, dateRange[1]])}
                className="w-full rounded-md border border-input bg-background/65 px-2 py-1.5 font-mono text-xs text-foreground"
              />
              <input
                type="date"
                value={dateRange[1]}
                min={range.start}
                max={range.end}
                onChange={(e) => setDateRange([dateRange[0], e.target.value])}
                className="w-full rounded-md border border-input bg-background/65 px-2 py-1.5 font-mono text-xs text-foreground"
              />
            </div>
          </div>
        )}

        <div className="mt-5 rounded-lg border border-signal-copper/20 bg-signal-copper/8 p-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-signal-copper">Link state</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {subreddits.length ? `${subreddits.length} active filters` : "Full network scan"}
          </p>
        </div>
      </div>
    </aside>
  );
}
