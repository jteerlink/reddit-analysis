"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useFilterStore } from "@/lib/store";
import { parentColor } from "@/lib/utils";
import type { EmbeddingMapResponse, EmbeddingPoint, SubredditCategoriesResponse } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const SENTIMENT_CLASS: Record<string, string> = {
  positive: "bg-emerald-400",
  neutral: "bg-slate-300",
  negative: "bg-red-400",
};

const SENTIMENT_OPTIONS = ["all", "positive", "neutral", "negative"] as const;
const COLOR_MODES = ["parent", "cluster", "sentiment"] as const;
type ColorMode = (typeof COLOR_MODES)[number];

const CLUSTER_COLORS = [
  "#31d38f", "#d97757", "#4285f4", "#a78bfa", "#f59e0b",
  "#10a37f", "#e26464", "#76b900", "#94a3b8", "#f472b6",
];

function clusterColor(clusterId: number | null | undefined) {
  if (clusterId == null || Number.isNaN(clusterId)) return CLUSTER_COLORS[0];
  return CLUSTER_COLORS[Math.abs(clusterId) % CLUSTER_COLORS.length];
}

function pointDateInRange(date: string | null | undefined, range: [string, string]) {
  if (!date) return true;
  const [start, end] = range;
  return (!start || date >= start) && (!end || date <= end);
}

function pointMatchesSearch(point: EmbeddingPoint, search: string) {
  const term = search.trim().toLowerCase();
  if (!term) return true;
  return [point.id, point.subreddit, point.sentiment, point.preview, String(point.topic_id ?? point.cluster_id)]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(term));
}

export default function EmbeddingMapPage() {
  const { data } = useSWR<EmbeddingMapResponse>("/api/analysis/embedding-map?limit=5000", fetcher);
  const { data: categories } = useSWR<SubredditCategoriesResponse>("/api/subreddits/categories", fetcher);
  const { subreddits, setSubreddits, parents, setParents, dateRange, setDateRange } = useFilterStore();
  const [sentiment, setSentiment] = useState<(typeof SENTIMENT_OPTIONS)[number]>("all");
  const [topicFilter, setTopicFilter] = useState<number | "all">("all");
  const [search, setSearch] = useState("");
  const [colorMode, setColorMode] = useState<ColorMode>("parent");
  const [hoveredPoint, setHoveredPoint] = useState<EmbeddingPoint | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<EmbeddingPoint | null>(null);
  const points = data?.items ?? [];

  const subredditToParent = useMemo(() => {
    const map = new Map<string, string>();
    for (const parent of categories?.parents ?? []) {
      for (const sub of parent.subreddits) {
        map.set(sub, parent.id);
      }
    }
    return map;
  }, [categories]);

  const topicOptions = useMemo(() => {
    const counts = new Map<number, number>();
    for (const point of points) {
      const topicId = point.topic_id ?? point.cluster_id;
      if (topicId == null) continue;
      counts.set(topicId, (counts.get(topicId) ?? 0) + 1);
    }
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
      .map(([topicId, count]) => ({ topicId, count }));
  }, [points]);

  const filteredPoints = useMemo(() => {
    return points.filter((point) => {
      if (sentiment !== "all" && point.sentiment !== sentiment) return false;
      if (topicFilter !== "all" && (point.topic_id ?? point.cluster_id) !== topicFilter) return false;
      if (subreddits.length && (!point.subreddit || !subreddits.includes(point.subreddit))) return false;
      if (parents.length) {
        const pid = point.parent_id ?? (point.subreddit ? subredditToParent.get(point.subreddit) : null);
        if (!pid || !parents.includes(pid)) return false;
      }
      if (!pointDateInRange(point.date, dateRange)) return false;
      return pointMatchesSearch(point, search);
    });
  }, [points, sentiment, topicFilter, subreddits, parents, dateRange, search, subredditToParent]);

  const activePoint = selectedPoint ?? hoveredPoint;
  const xs = filteredPoints.map((point) => point.x);
  const ys = filteredPoints.map((point) => point.y);
  const minX = Math.min(...xs, -1);
  const maxX = Math.max(...xs, 1);
  const minY = Math.min(...ys, -1);
  const maxY = Math.max(...ys, 1);
  const hasFilters = sentiment !== "all" || topicFilter !== "all" || !!search.trim() || subreddits.length > 0 || parents.length > 0 || !!dateRange[0] || !!dateRange[1];

  const resetLocalFilters = () => {
    setSentiment("all");
    setTopicFilter("all");
    setSearch("");
    setSubreddits([]);
    setParents([]);
    setDateRange(["", ""]);
    setHoveredPoint(null);
    setSelectedPoint(null);
  };

  function pointFill(point: EmbeddingPoint) {
    if (colorMode === "sentiment") {
      return SENTIMENT_CLASS[point.sentiment ?? ""] ?? "bg-signal-copper";
    }
    if (colorMode === "cluster") {
      return null;
    }
    return null;
  }

  function pointStyle(point: EmbeddingPoint): React.CSSProperties | undefined {
    if (colorMode === "parent") {
      const pid = point.parent_id ?? (point.subreddit ? subredditToParent.get(point.subreddit) : null);
      return { background: parentColor(pid) };
    }
    if (colorMode === "cluster") {
      return { background: clusterColor(point.topic_id ?? point.cluster_id) };
    }
    return undefined;
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Semantic Space"
        title="Embedding map"
        subtitle="Projected MiniLM conversation embeddings — colour by parent, cluster, or sentiment."
      />

      <ChartCard
        title="Conversation map"
        subtitle={`${filteredPoints.length.toLocaleString()} of ${points.length.toLocaleString()} conversations / ${data?.provenance?.algorithm ?? "embedding projection"}`}
        action={
          <Button variant="outline" size="sm" onClick={resetLocalFilters} disabled={!hasFilters}>
            Reset
          </Button>
        }
      >
        {data ? (
          <>
            {data.state !== "ready" && (
              <div className="mb-3 rounded-md border border-signal-yellow/25 bg-signal-yellow/10 px-3 py-2 text-xs text-signal-yellow">
                {data.provenance?.detail ?? data.state.replace("_", " ")}
              </div>
            )}

            <div className="mb-4 grid gap-3 xl:grid-cols-[minmax(260px,1fr)_auto]">
              <div className="grid gap-2 md:grid-cols-[minmax(180px,1fr)_auto]">
                <Input
                  aria-label="Search embedding points"
                  placeholder="Search preview, subreddit, topic, or id..."
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
                <div className="flex flex-wrap gap-1">
                  {SENTIMENT_OPTIONS.map((option) => (
                    <Button
                      key={option}
                      type="button"
                      size="sm"
                      variant={sentiment === option ? "secondary" : "outline"}
                      onClick={() => setSentiment(option)}
                    >
                      {option}
                    </Button>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-1">
                <span className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">colour</span>
                {COLOR_MODES.map((mode) => (
                  <Button
                    key={mode}
                    type="button"
                    size="sm"
                    variant={colorMode === mode ? "secondary" : "outline"}
                    onClick={() => setColorMode(mode)}
                  >
                    {mode}
                  </Button>
                ))}
                <Button
                  type="button"
                  size="sm"
                  variant={topicFilter === "all" ? "secondary" : "outline"}
                  onClick={() => setTopicFilter("all")}
                >
                  all topics
                </Button>
                {topicOptions.map(({ topicId, count }) => (
                  <Button
                    key={topicId}
                    type="button"
                    size="sm"
                    variant={topicFilter === topicId ? "secondary" : "outline"}
                    onClick={() => setTopicFilter(topicId)}
                  >
                    #{topicId}
                    <span className="font-mono text-[10px] text-muted-foreground">{count}</span>
                  </Button>
                ))}
              </div>
            </div>

            <div className="mb-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">{filteredPoints.length.toLocaleString()} visible</Badge>
              {!!parents.length && <Badge variant="outline">{parents.length} parent filters</Badge>}
              {!!subreddits.length && <Badge variant="outline">{subreddits.length} subreddit filters</Badge>}
              {(dateRange[0] || dateRange[1]) && <Badge variant="outline">{dateRange[0] || "start"} to {dateRange[1] || "end"}</Badge>}
              {selectedPoint && <Badge variant="secondary">Pinned {selectedPoint.id}</Badge>}
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
              <div className="relative h-[620px] overflow-hidden rounded-md border border-border bg-background">
                <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.045)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.045)_1px,transparent_1px)] bg-[size:64px_64px]" />
                {filteredPoints.map((point) => {
                  const rawLeft = ((point.x - minX) / Math.max(maxX - minX, 0.001)) * 96 + 2;
                  const rawTop = 98 - ((point.y - minY) / Math.max(maxY - minY, 0.001)) * 96;
                  const isActive = activePoint?.id === point.id;
                  const fallbackClass = pointFill(point);
                  return (
                    <button
                      key={point.id}
                      type="button"
                      aria-label={`Inspect ${point.subreddit ?? "unknown"} topic ${point.topic_id ?? point.cluster_id}`}
                      onPointerEnter={() => setHoveredPoint(point)}
                      onPointerLeave={() => setHoveredPoint(null)}
                      onMouseEnter={() => setHoveredPoint(point)}
                      onMouseLeave={() => setHoveredPoint(null)}
                      onFocus={() => setHoveredPoint(point)}
                      onBlur={() => setHoveredPoint(null)}
                      onClick={() => setSelectedPoint((current) => current?.id === point.id ? null : point)}
                      className={`absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-1 ring-black/40 transition-transform hover:z-20 hover:scale-150 focus-visible:z-20 focus-visible:scale-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-green ${fallbackClass ?? ""} ${isActive ? "z-20 scale-150 opacity-100 ring-2 ring-foreground" : "opacity-72"}`}
                      style={{ left: `${rawLeft}%`, top: `${rawTop}%`, ...pointStyle(point) }}
                    />
                  );
                })}
                {hoveredPoint && (
                  <div className="pointer-events-none absolute left-3 top-3 z-30 max-w-sm rounded-md border border-signal-copper/35 bg-[#081816]/95 px-3 py-2 text-xs shadow-2xl">
                    <p className="font-mono text-signal-copper">{hoveredPoint.subreddit ?? "unknown"} / topic {hoveredPoint.topic_id ?? hoveredPoint.cluster_id}</p>
                    <p className="mt-1 text-foreground">{hoveredPoint.preview ?? "No preview available"}</p>
                    <p className="mt-2 font-mono text-muted-foreground">{hoveredPoint.date ?? "no date"} / {hoveredPoint.sentiment ?? "unscored"}</p>
                  </div>
                )}
                {!filteredPoints.length && (
                  <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
                    {points.length ? "No conversations match the active filters" : "Run the embedding map backfill to populate projected conversations"}
                  </div>
                )}
              </div>

              <aside className="min-h-[220px] rounded-md border border-border bg-background/45 p-4">
                {activePoint ? (
                  <div className="space-y-4">
                    <div>
                      <p className="command-label">Selected conversation</p>
                      <h2 className="mt-1 break-all font-mono text-sm text-foreground">{activePoint.id}</h2>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">{activePoint.sentiment ?? "unscored"}</Badge>
                      <Badge variant="outline">{activePoint.subreddit ?? "unknown"}</Badge>
                      {activePoint.parent_id && <Badge variant="outline">{activePoint.parent_id}</Badge>}
                      <Badge variant="outline">topic {activePoint.topic_id ?? activePoint.cluster_id}</Badge>
                    </div>
                    <dl className="grid grid-cols-2 gap-3 text-xs">
                      <div>
                        <dt className="text-muted-foreground">Date</dt>
                        <dd className="mt-1 font-mono text-foreground">{activePoint.date ?? "none"}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Cluster</dt>
                        <dd className="mt-1 font-mono text-foreground">#{activePoint.cluster_id}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">X</dt>
                        <dd className="mt-1 font-mono text-foreground">{activePoint.x.toFixed(3)}</dd>
                      </div>
                      <div>
                        <dt className="text-muted-foreground">Y</dt>
                        <dd className="mt-1 font-mono text-foreground">{activePoint.y.toFixed(3)}</dd>
                      </div>
                    </dl>
                    <div>
                      <p className="text-xs text-muted-foreground">Preview</p>
                      <p className="mt-2 text-sm leading-6 text-foreground">{activePoint.preview ?? "No preview available."}</p>
                    </div>
                    {selectedPoint && (
                      <Button type="button" variant="outline" size="sm" onClick={() => setSelectedPoint(null)}>
                        Unpin point
                      </Button>
                    )}
                  </div>
                ) : (
                  <div className="grid h-full place-items-center text-center text-sm text-muted-foreground">
                    Hover or click a point to inspect subreddit, topic, sentiment, date, and preview text.
                  </div>
                )}
              </aside>
            </div>
          </>
        ) : (
          <Skeleton className="h-[740px] w-full" />
        )}
      </ChartCard>
    </div>
  );
}
