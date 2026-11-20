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
  postId: string | null;
  topicId: number | null;
  topicLabel: string | null;
};

const EMPTY_ROUTE_FILTERS: RouteFilters = {
  subreddits: [],
  parents: [],
  postId: null,
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
    postId: params.get("post_id"),
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

function originalText(row: Post | SemanticSearchResult): string {
  if (row.original_text) return row.original_text;
  if ("text_preview" in row && row.text_preview) return row.text_preview;
  return row.clean_text || "No source text available.";
}

function sourceDate(row: Post | SemanticSearchResult): string {
  return row.timestamp?.slice(0, 16).replace("T", " ") ?? row.date ?? "n/a";
}

function safeSourceUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
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
  const scopedByRoute = !!routeFilters.postId || !!routeFilters.topicId || !!routeFilters.subreddits.length || !!routeFilters.parents.length;

  useEffect(() => {
    const filters = readRouteFilters();
    setKeyword(filters.keyword);
    setLabel(filters.label);
    setContentType(filters.contentType);
    setMode(filters.mode);
    setRouteFilters({
      subreddits: filters.subreddits,
      parents: filters.parents,
      postId: filters.postId,
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
  if (routeFilters.postId) params.set("post_id", routeFilters.postId);
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(page * PAGE_SIZE));

  const semanticParams = new URLSearchParams();
  effectiveSubreddits.forEach((subreddit) => semanticParams.append("subreddits", subreddit));
  effectiveParents.forEach((parent) => semanticParams.append("parents", parent));
  if (dateRange[0]) semanticParams.set("start_date", dateRange[0]);
  if (dateRange[1]) semanticParams.set("end_date", dateRange[1]);
  semanticParams.set("q", keyword);
  semanticParams.set("limit", String(PAGE_SIZE));
  if (label !== "all") semanticParams.set("label", label);
  if (contentType !== "both") semanticParams.set("content_type", contentType);

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
    if (routeFilters.postId) parts.push(`record ${routeFilters.postId}`);
    if (routeFilters.topicId != null) parts.push(routeFilters.topicLabel ?? `Topic ${routeFilters.topicId}`);
    if (effectiveParents.length) parts.push(`${effectiveParents.length} parent${effectiveParents.length === 1 ? "" : "s"}`);
    if (effectiveSubreddits.length) parts.push(`${effectiveSubreddits.length} subreddit${effectiveSubreddits.length === 1 ? "" : "s"}`);
    return parts.join(" / ");
  }, [effectiveParents.length, effectiveSubreddits.length, routeFilters.postId, routeFilters.topicId, routeFilters.topicLabel]);

  function exportCSV() {
    if (!rows?.length) return;
    const cols = ["date", "timestamp", "subreddit", "content_type", "label", "confidence", "title", "original_text", "clean_text", "source_url"];
    const csvRows = rows.map((p) => cols.map((c) => JSON.stringify((p as unknown as Record<string, unknown>)[c] ?? (c === "original_text" ? originalText(p) : ""))).join(","));
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
                <th className="pb-2 font-medium w-32">Collected</th>
                <th className="pb-2 font-medium w-32">Subreddit</th>
                <th className="pb-2 font-medium w-20">Type</th>
                <th className="pb-2 font-medium w-24">Label</th>
                <th className="pb-2 font-medium w-16">Conf.</th>
                {mode === "semantic" && <th className="pb-2 font-medium w-20">Score</th>}
                <th className="pb-2 font-medium min-w-72">Original source</th>
              </tr>
            </thead>
            <tbody>
              {rows?.map((p, i) => {
                const semantic = p as SemanticSearchResult;
                const text = originalText(p);
                const cleanText = p.clean_text;
                const sourceUrl = safeSourceUrl(p.source_url);
                return (
                <tr key={p.id || i} className="border-b border-border/50 last:border-0 align-top">
                  <td className="py-2 text-muted-foreground tabular-nums">{sourceDate(p)}</td>
                  <td className="py-2 text-muted-foreground">{p.subreddit}</td>
                  <td className="py-2 text-muted-foreground">{p.content_type}</td>
                  <td className="py-2">
                    <span className={`inline-block rounded px-2 py-0.5 text-xs border ${LABEL_COLORS[p.label ?? ""] ?? ""}`}>{p.label ?? "n/a"}</span>
                  </td>
                  <td className="py-2 tabular-nums">{p.confidence?.toFixed(2) ?? "n/a"}</td>
                  {mode === "semantic" && <td className="py-2 tabular-nums">{semantic.score.toFixed(2)}</td>}
                  <td className="py-2">
                    <div className="max-w-xl space-y-1.5">
                      {p.title && <p className="font-medium text-foreground">{p.title}</p>}
                      <p className="whitespace-pre-wrap text-sm leading-5 text-foreground">{text}</p>
                      {sourceUrl && (
                        <a href={sourceUrl} target="_blank" rel="noreferrer" className="inline-flex text-xs text-signal-copper underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-green">
                          Open original thread
                        </a>
                      )}
                      {cleanText && cleanText !== text && (
                        <details className="rounded border border-border/60 bg-muted/20 px-2 py-1 text-xs text-muted-foreground">
                          <summary className="cursor-pointer font-medium text-foreground">Show cleaned model input</summary>
                          <p className="mt-1 whitespace-pre-wrap leading-5">{cleanText}</p>
                        </details>
                      )}
                    </div>
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
