"use client";

import { useState } from "react";
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

export default function DeepDivePage() {
  const { subreddits, dateRange } = useFilterStore();
  const [keyword, setKeyword] = useState("");
  const [label, setLabel] = useState("all");
  const [contentType, setContentType] = useState("both");
  const [mode, setMode] = useState<"keyword" | "semantic">("keyword");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  const params = new URLSearchParams();
  if (keyword) params.set("keyword", keyword);
  subreddits.forEach((s) => params.append("subreddits", s));
  if (dateRange[0]) params.set("start", dateRange[0]);
  if (dateRange[1]) params.set("end", dateRange[1]);
  if (label !== "all") params.set("label", label);
  if (contentType !== "both") params.set("content_type", contentType);
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(page * PAGE_SIZE));

  const semanticParams = new URLSearchParams();
  semanticParams.set("q", keyword);
  semanticParams.set("limit", String(PAGE_SIZE));

  const { data: posts } = useSWR<Post[]>(
    mode === "keyword" ? `/api/posts/search?${params}` : null,
    fetcher
  );
  const { data: semanticResults } = useSWR<SemanticSearchResponse>(
    mode === "semantic" && keyword.trim() ? `/api/analysis/semantic-search?${semanticParams}` : null,
    fetcher
  );
  const rows = mode === "semantic" ? semanticResults?.items : posts;

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

      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-48">
          <Input placeholder="Search keyword…" value={keyword} onChange={(e) => { setKeyword(e.target.value); setPage(0); }} />
        </div>
        <div className="flex gap-1">
          {(["keyword", "semantic"] as const).map((option) => (
            <button
              key={option}
              onClick={() => { setMode(option); setPage(0); }}
              className={`px-3 py-1.5 rounded text-xs transition-colors ${mode === option ? "bg-amber-500 text-black font-medium" : "bg-muted text-muted-foreground hover:text-foreground"}`}
            >
              {option}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {["all", "positive", "neutral", "negative"].map((l) => (
            <button key={l} onClick={() => { setLabel(l); setPage(0); }} className={`px-3 py-1.5 rounded text-xs transition-colors ${label === l ? "bg-amber-500 text-black font-medium" : "bg-muted text-muted-foreground hover:text-foreground"}`}>{l}</button>
          ))}
        </div>
        <div className="flex gap-1">
          {["both", "post", "comment"].map((ct) => (
            <button key={ct} onClick={() => { setContentType(ct); setPage(0); }} className={`px-3 py-1.5 rounded text-xs transition-colors ${contentType === ct ? "bg-amber-500 text-black font-medium" : "bg-muted text-muted-foreground hover:text-foreground"}`}>{ct}</button>
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
                  <td className="py-2 text-muted-foreground max-w-xs truncate">{text}</td>
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
