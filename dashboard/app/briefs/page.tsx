"use client";

import useSWR from "swr";
import { AlertTriangle, Compass, FileText, Newspaper, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { Badge } from "@/components/ui/badge";
import type { AnalystBrief, AnalystBriefsResponse, BriefSection, FreshnessResponse, ModelRegistryResponse } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const SECTION_STYLES: Record<string, { icon: LucideIcon; accent: string }> = {
  "executive summary": { icon: FileText, accent: "text-signal-green border-signal-green/30" },
  "key findings": { icon: Newspaper, accent: "text-signal-copper border-signal-copper/30" },
  "notable trends": { icon: TrendingUp, accent: "text-signal-blue border-signal-blue/30" },
  "risks & anomalies": { icon: AlertTriangle, accent: "text-signal-red border-signal-red/30" },
  "outlook": { icon: Compass, accent: "text-signal-yellow border-signal-yellow/30" },
};

function styleForSection(title: string) {
  const key = title.toLowerCase().trim();
  return SECTION_STYLES[key];
}

function BriefSectionRow({ section, index }: { section: BriefSection; index: number }) {
  const style = styleForSection(String(section.title ?? ""));
  const Icon = style?.icon ?? FileText;
  const accent = style?.accent ?? "text-muted-foreground border-border";
  return (
    <section className="border-t border-border pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-center gap-2">
        <span className={`grid size-6 place-items-center rounded-md border bg-card/70 ${accent}`}>
          <Icon className="size-3.5" aria-hidden="true" />
        </span>
        <h3 className="text-sm font-semibold text-foreground">{String(section.title ?? `Section ${index + 1}`)}</h3>
      </div>
      <p className="mt-2 whitespace-pre-line text-sm leading-6 text-muted-foreground">{String(section.body ?? "")}</p>
    </section>
  );
}

export default function BriefsPage() {
  const { data: briefs } = useSWR<AnalystBriefsResponse>("/api/analysis/briefs?limit=10", fetcher);
  const { data: latest } = useSWR<AnalystBrief>("/api/analysis/briefs/latest", fetcher);
  const { data: freshness } = useSWR<FreshnessResponse>("/api/analysis/freshness", fetcher);
  const { data: models } = useSWR<ModelRegistryResponse>("/api/analysis/model-registry", fetcher);
  const items = briefs?.items?.length ? briefs.items : latest ? [latest] : [];

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Briefs"
        title="Analyst brief"
        subtitle="Structured intelligence brief covering the latest period. Pre-ab-v2 briefs render in single-section fallback styling."
      />

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          {briefs?.state && briefs.state !== "ready" && (
            <div className="rounded-md border border-signal-yellow/25 bg-signal-yellow/10 px-3 py-2 text-xs text-signal-yellow">
              {briefs.provenance?.detail ?? briefs.state.replace("_", " ")}
            </div>
          )}

          {items.length ? items.map((brief) => (
            <ChartCard
              key={`${brief.provenance?.artifact_id ?? brief.brief_id}-${brief.provenance?.label ?? "brief"}`}
              title={brief.headline}
              subtitle={brief.generated_at ?? "artifact timestamp unavailable"}
            >
              <div className="mb-4 flex flex-wrap gap-2">
                <Badge variant="secondary">{brief.provenance?.label === "llm_artifact" ? "LLM" : "Deterministic"}</Badge>
                {brief.model_name && <Badge variant="outline">{brief.model_name}</Badge>}
                {brief.provenance?.provider && <Badge variant="outline">{brief.provenance.provider}</Badge>}
              </div>
              <div className="space-y-3">
                {brief.sections?.length ? brief.sections.map((section, index) => (
                  <BriefSectionRow key={index} section={section} index={index} />
                )) : (
                  <div className="grid h-32 place-items-center text-sm text-muted-foreground">
                    Brief artifact has no sections.
                  </div>
                )}
              </div>
            </ChartCard>
          )) : (
            <ChartCard title="No analyst briefs" subtitle="waiting for artifact">
              <div className="grid h-40 place-items-center text-sm text-muted-foreground">
                No brief artifact has been generated yet.
              </div>
            </ChartCard>
          )}
        </div>

        <div className="space-y-4">
          <ChartCard title="Artifact freshness">
            <div className="space-y-2 font-mono text-xs text-muted-foreground">
              <p>state: {freshness?.state ?? "unknown"}</p>
              <p>success: {freshness?.succeeded ?? 0}</p>
              <p>queued: {freshness?.queued ?? 0}</p>
              <p>running: {freshness?.running ?? 0}</p>
              <p>failed: {freshness?.failed ?? 0}</p>
              <p>latest success: {freshness?.latest_success_at ?? "none"}</p>
              <p>llm: {freshness?.llm_enrichment_available ? "configured" : freshness?.llm_reason ?? "unknown"}</p>
            </div>
          </ChartCard>
          <ChartCard title="Ollama provider">
            <div className="space-y-2 font-mono text-xs text-muted-foreground">
              <p>host: {models?.default_host ?? "unknown"}</p>
              <p>cloud configured: {models?.cloud_configured ? "yes" : "no"}</p>
              <p>local override: {models?.local_override ? "yes" : "no"}</p>
              <p>models: {models?.models.length ?? 0}</p>
            </div>
          </ChartCard>
        </div>
      </div>
    </div>
  );
}
