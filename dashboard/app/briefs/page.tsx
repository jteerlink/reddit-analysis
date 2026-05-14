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

function asStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item ?? "").trim()).filter(Boolean);
  }
  const text = String(value ?? "").trim();
  return text ? [text] : [];
}

function EvidenceList({ section }: { section: BriefSection }) {
  const claims = asStringList(section.claims);
  const drivers = asStringList(section.drivers);
  const implications = asStringList(section.implications);
  const evidence = Array.isArray(section.evidence) ? section.evidence : [];
  const delta = String(section.delta ?? "").trim();
  const evidenceGap = String(section.evidence_gap ?? "").trim();
  const hasExtras = claims.length || drivers.length || implications.length || evidence.length || delta || evidenceGap;

  if (!hasExtras) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2 rounded-md border border-border/70 bg-muted/20 p-3 text-xs text-muted-foreground">
      {delta && (
        <div>
          <span className="font-semibold text-foreground">Delta: </span>
          <span>{delta}</span>
          {section.delta_source ? <Badge variant="outline" className="ml-2">{String(section.delta_source)}</Badge> : null}
        </div>
      )}
      {claims.length ? <MetadataList label="Claims" items={claims} /> : null}
      {drivers.length ? <MetadataList label="Drivers" items={drivers} /> : null}
      {implications.length ? <MetadataList label="Implications" items={implications} /> : null}
      {evidence.length ? (
        <div>
          <p className="mb-1 font-semibold text-foreground">Evidence</p>
          <ul className="space-y-1">
            {evidence.map((item, index) => (
              <li key={`${item.anchor_type}-${item.anchor_id}-${index}`} className="rounded border border-border/60 bg-card/60 px-2 py-1">
                <span className="font-mono text-[11px] text-foreground">{item.anchor_type}:{item.anchor_id}</span>
                {item.label ? <span> — {item.label}</span> : null}
                {item.snippet ? <span className="block">{item.snippet}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {evidenceGap ? (
        <div className="rounded border border-signal-yellow/20 bg-signal-yellow/10 px-2 py-1 text-signal-yellow">
          Evidence gap: {evidenceGap}
        </div>
      ) : null}
    </div>
  );
}

function MetadataList({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1 font-semibold text-foreground">{label}</p>
      <ul className="list-disc space-y-1 pl-4">
        {items.map((item, index) => <li key={`${label}-${index}`}>{item}</li>)}
      </ul>
    </div>
  );
}

type BriefBodyBlock =
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] };

function parseBriefBody(body: string): BriefBodyBlock[] {
  const blocks: BriefBodyBlock[] = [];
  const lines = body.replace(/\r\n/g, "\n").split("\n");
  let paragraph: string[] = [];
  let listItems: string[] = [];

  const flushParagraph = () => {
    const text = paragraph.join(" ").trim();
    if (text) blocks.push({ type: "paragraph", text });
    paragraph = [];
  };
  const flushList = () => {
    if (listItems.length) blocks.push({ type: "list", items: listItems });
    listItems = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }
    const bullet = line.match(/^(?:[-*•]|\d+[.)])\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      listItems.push(bullet[1].trim());
      continue;
    }
    flushList();
    paragraph.push(line.replace(/^#{1,6}\s+/, ""));
  }
  flushParagraph();
  flushList();
  return blocks;
}

function BriefBody({ body }: { body: string }) {
  const blocks = parseBriefBody(body);
  if (!blocks.length) return null;
  return (
    <div className="mt-2 space-y-2 text-sm leading-6 text-muted-foreground">
      {blocks.map((block, index) => (
        block.type === "list" ? (
          <ul key={`list-${index}`} className="list-disc space-y-1 pl-5">
            {block.items.map((item, itemIndex) => <li key={`${index}-${itemIndex}`}>{item}</li>)}
          </ul>
        ) : (
          <p key={`paragraph-${index}`}>{block.text}</p>
        )
      ))}
    </div>
  );
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
      <BriefBody body={String(section.body ?? "")} />
      <EvidenceList section={section} />
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
