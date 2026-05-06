"use client";

import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { ChartCard } from "@/components/shared/ChartCard";
import type { AnalystBrief, FreshnessResponse, ModelRegistryResponse } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function BriefsPage() {
  const { data: brief } = useSWR<AnalystBrief>("/api/analysis/briefs/latest", fetcher);
  const { data: freshness } = useSWR<FreshnessResponse>("/api/analysis/freshness", fetcher);
  const { data: models } = useSWR<ModelRegistryResponse>("/api/analysis/model-registry", fetcher);

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="Briefs"
        title="Analyst brief"
        subtitle="Latest persisted summary from the artifact pipeline. The page renders even when LLM credentials are not configured."
      />

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <ChartCard title={brief?.headline ?? "No analyst brief"} subtitle={brief?.generated_at ?? "waiting for artifact"}>
          {brief?.state && brief.state !== "ready" && (
            <div className="mb-3 rounded-md border border-signal-yellow/25 bg-signal-yellow/10 px-3 py-2 text-xs text-signal-yellow">
              {brief.provenance?.detail ?? brief.state.replace("_", " ")}
            </div>
          )}
          <div className="space-y-4">
            {brief?.sections?.length ? brief.sections.map((section, index) => (
              <section key={index} className="rounded-md border border-border bg-background/35 p-4">
                <h3 className="text-sm font-semibold text-foreground">{String(section.title ?? `Section ${index + 1}`)}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{String(section.body ?? "")}</p>
              </section>
            )) : (
              <div className="grid h-40 place-items-center text-sm text-muted-foreground">
                No brief artifact has been generated yet.
              </div>
            )}
          </div>
        </ChartCard>

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
