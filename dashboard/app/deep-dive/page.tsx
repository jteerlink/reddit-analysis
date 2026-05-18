"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { useFilterStore } from "@/lib/store";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { Post, SemanticSearchResponse, SemanticSearchResult } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const LABEL_COLORS: Record<string, string> = {
  positive: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  neutral: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  negative: "bg-red-500/10 text-red-400 border-red-500/20",
};

type RouteFilters = {
  subreddits: string[];
  parents: string[];
  topicId: number | null;
  topicLabel: string | null;
};

const EMPTY_ROUTE_FILTERS: RouteFilters = {
  subreddits: [],
  parents: [],
  topicId: null,
  topicLabel: null,
};

function readRouteFilters(): RouteFilters & {
  keyword: string;
  label: string;
  contentType: string;
  mode: "keyword" | "semantic";
} {
  if (typeof window === "undefined") {
    return { ...EMPTY_ROUTE_FILTERS, keyword: "", label: "all", contentType: "both", mode: "keyword" };
  }

  const params = new URLSearchParams(window.location.search);
  const topicId = Number(params.get("topic_id"));
  const mode = params.get("mode") === "semantic" ? "semantic" : "keyword";
  return {
    keyword: params.get("keyword") ?? "",
    label: params.get("label") ?? "all",
    contentType: params.get("content_type") ?? "both",
    mode,
    subreddits: params.getAll("subreddits"),
    parents: params.getAll("parents"),
    topicId: Number.isFinite(topicId) ? topicId : null,
    topicLabel: params.get("topic_label"),
  };
}

function SegmentButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`px-3 py-1.5 rounded text-xs transition-colors ${active ? "bg-amber-500 text-black font-medium" : "bg-muted text-muted-foreground hover:text-foreground"}`}
    >
      {children}
    </button>
  );
}

function TextPreview({ text }: { text: string }) {
  return (
    <div className="group relative max-w-xs">
      <span className="block truncate text-muted-foreground" tabIndex={0}>
        {text}
      </span>
      <div className="pointer-events-none absolute bottom-full left-0 z-30 mb-2 hidden max-h-72 w-[min(34rem,80vw)] overflow-y-auto rounded-md border border-signal-copper/35 bg-[#081816]/98 px-3 py-2 text-xs leading-5 text-foreground shadow-2xl group-hover:block group-focus-within:block">
        {text}
      </div>
    </div>
  );
}

export default function DeepDivePage() {
  const { subreddits, parents, dateRange } = useFilterStore();
  const [ready, setReady] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [label, setLabel] = useState("all");
  const [contentType, setContentType] = useState("both");
  const [mode, setMode] = useState<"keyword" | "semantic">("keyword");
  const [routeFilters, setRouteFilters] = useState<RouteFilters>(EMPTY_ROUTE_FILTERS);
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;
  const effectiveSubreddits = routeFilters.subreddits.length ? routeFilters.subreddits : subreddits;
  const effectiveParents = routeFilters.parents.length ? routeFilters.parents : parents;
  const scopedByRoute = !!routeFilters.topicId || !!routeFilters.subreddits.length || !!routeFilters.parents.length;

  useEffect(() => {
    const filters = readRouteFilters();
    setKeyword(filters.keyword);
    setLabel(filters.label);
    setContentType(filters.contentType);
    setMode(filters.mode);
    setRouteFilters({
      subreddits: filters.subreddits,
      parents: filters.parents,
      topicId: filters.topicId,
      topicLabel: filters.topicLabel,
    });
    setReady(true);
  }, []);

  const params = new URLSearchParams();
  if (keyword) params.set("keyword", keyword);
  effectiveSubreddits.forEach((s) => params.append("subreddits", s));
  effectiveParents.forEach((p) => params.append("parents", p));
  if (dateRange[0]) params.set("start", dateRange[0]);
  if (dateRange[1]) params.set("end", dateRange[1]);
  if (label !== "all") params.set("label", label);
  if (contentType !== "both") params.set("content_type", contentType);
  if (routeFilters.topicId != null) params.set("topic_id", String(routeFilters.topicId));
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(page * PAGE_SIZE));

  const semanticParams = new URLSearchParams();
  semanticParams.set("q", keyword);
  semanticParams.set("limit", String(PAGE_SIZE));

  const { data: posts } = useSWR<Post[]>(
    ready && mode === "keyword" ? `/api/posts/search?${params}` : null,
    fetcher
  );
  const { data: semanticResults } = useSWR<SemanticSearchResponse>(
    ready && mode === "semantic" && keyword.trim() ? `/api/analysis/semantic-search?${semanticParams}` : null,
    fetcher
  );
  const rows = mode === "semantic" ? semanticResults?.items : posts;
  const filterSummary = useMemo(() => {
    const parts = [];
    if (routeFilters.topicId != null) parts.push(routeFilters.topicLabel ?? `Topic ${routeFilters.topicId}`);
    if (effectiveParents.length) parts.push(`${effectiveParents.length} parent${effectiveParents.length === 1 ? "" : "s"}`);
    if (effectiveSubreddits.length) parts.push(`${effectiveSubreddits.length} subreddit${effectiveSubreddits.length === 1 ? "" : "s"}`);
    return parts.join(" / ");
  }, [effectiveParents.length, effectiveSubreddits.length, routeFilters.topicId, routeFilters.topicLabel]);

  function exportCSV() {
    if (!rows?.length) return;
    const cols = ["date", "subreddit", "content_type", "label", "confidence", "clean_text"];
    const csvRows = rows.map((p) => cols.map((c) => JSON.stringify((p as unknown as Record<string, unknown>)[c] ?? (p as SemanticSearchResult).text_preview ?? "")).join(","));
    const blob = new Blob([cols.join(",") + "\n" + csvRows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "deep_dive.csv"; a.click();
  }

  function exportJSON() {
    if (!rows?.length) return;
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "deep_dive.json"; a.click();
  }

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Search" title="Deep dive" subtitle="Keyword and semantic search across preprocessed posts and comments." />

      {scopedByRoute && filterSummary && (
        <div className="rounded-md border border-signal-green/25 bg-signal-green/10 px-3 py-2 text-xs text-signal-green">
          Showing results filtered to {filterSummary}.
        </div>
      )}

      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-48">
          <Input placeholder="Search keyword…" value={keyword} onChange={(e) => { setKeyword(e.target.value); setPage(0); }} />
        </div>
        <div className="flex gap-1" role="group" aria-label="Search mode">
          {(["keyword", "semantic"] as const).map((option) => (
            <SegmentButton
              key={option}
              active={mode === option}
              onClick={() => { setMode(option); setPage(0); }}
            >
              {option}
            </SegmentButton>
          ))}
        </div>
        <div className="flex gap-1" role="group" aria-label="Sentiment label">
          {["all", "positive", "neutral", "negative"].map((l) => (
            <SegmentButton key={l} active={label === l} onClick={() => { setLabel(l); setPage(0); }}>{l}</SegmentButton>
          ))}
        </div>
        <div className="flex gap-1" role="group" aria-label="Content type">
          {["both", "post", "comment"].map((ct) => (
            <SegmentButton key={ct} active={contentType === ct} onClick={() => { setContentType(ct); setPage(0); }}>{ct}</SegmentButton>
          ))}
        </div>
        <button onClick={exportCSV} className="px-3 py-1.5 rounded text-xs bg-muted text-muted-foreground hover:text-foreground">CSV</button>
        <button onClick={exportJSON} className="px-3 py-1.5 rounded text-xs bg-muted text-muted-foreground hover:text-foreground">JSON</button>
      </div>

      <ChartCard title={`Results${rows ? ` (${rows.length} shown)` : ""}`}>
        {mode === "semantic" && semanticResults?.state && semanticResults.state !== "ready" && (
          <div className="mb-3 rounded-md border border-signal-yellow/25 bg-signal-yellow/10 px-3 py-2 text-xs text-signal-yellow">
            {semanticResults.provenance?.detail ?? semanticResults.state.replace("_", " ")}
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-border">
                <th className="pb-2 font-medium w-24">Date</th>
                <th className="pb-2 font-medium w-32">Subreddit</th>
                <th className="pb-2 font-medium w-20">Type</th>
                <th className="pb-2 font-medium w-24">Label</th>
                <th className="pb-2 font-medium w-16">Conf.</th>
                {mode === "semantic" && <th className="pb-2 font-medium w-20">Score</th>}
                <th className="pb-2 font-medium">Text</th>
              </tr>
            </thead>
            <tbody>
              {rows?.map((p, i) => {
                const semantic = p as SemanticSearchResult;
                const text = "text_preview" in p ? semantic.text_preview : (p as Post).clean_text;
                return (
                <tr key={i} className="border-b border-border/50 last:border-0 align-top">
                  <td className="py-2 text-muted-foreground tabular-nums">{p.date}</td>
                  <td className="py-2 text-muted-foreground">{p.subreddit}</td>
                  <td className="py-2 text-muted-foreground">{p.content_type}</td>
                  <td className="py-2">
                    <span className={`inline-block rounded px-2 py-0.5 text-xs border ${LABEL_COLORS[p.label ?? ""] ?? ""}`}>{p.label ?? "n/a"}</span>
                  </td>
                  <td className="py-2 tabular-nums">{p.confidence?.toFixed(2) ?? "n/a"}</td>
                  {mode === "semantic" && <td className="py-2 tabular-nums">{semantic.score.toFixed(2)}</td>}
                  <td className="py-2">
                    <TextPreview text={text} />
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="flex gap-2 mt-4 items-center text-sm">
          <button disabled={page === 0 || mode === "semantic"} onClick={() => setPage(page - 1)} className="px-3 py-1 rounded bg-muted disabled:opacity-40">← Prev</button>
          <span className="text-muted-foreground">Page {page + 1}</span>
          <button disabled={mode === "semantic" || !posts || posts.length < PAGE_SIZE} onClick={() => setPage(page + 1)} className="px-3 py-1 rounded bg-muted disabled:opacity-40">Next →</button>
        </div>
      </ChartCard>
    </div>
  );
}
