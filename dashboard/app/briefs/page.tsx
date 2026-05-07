"use client";

import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import { Badge } from "@/components/ui/badge";
import type { AnalystBrief, AnalystBriefsResponse, FreshnessResponse, ModelRegistryResponse } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

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
        subtitle="Latest persisted summary from the artifact pipeline. The page renders even when LLM credentials are not configured."
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
                  <section key={index} className="border-t border-border pt-3 first:border-t-0 first:pt-0">
                    <h3 className="text-sm font-semibold text-foreground">{String(section.title ?? `Section ${index + 1}`)}</h3>
                    <p className="mt-2 whitespace-pre-line text-sm leading-6 text-muted-foreground">{String(section.body ?? "")}</p>
                  </section>
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
