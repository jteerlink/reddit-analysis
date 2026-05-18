"use client";

import { useState } from "react";
import useSWR from "swr";
import { CheckCircle2, CircleDot, Database, GitBranch, MessageSquareText, Server, Workflow } from "lucide-react";
import type { PipelineHealthResponse } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const STAGE_ICONS = {
  Ingestion: CircleDot,
  Processing: Workflow,
  Sentiment: CheckCircle2,
  Topics: Database,
  Storage: Server,
};

function Sparkline({ alert = false, label, values }: { alert?: boolean; label: string; values: number[] }) {
  const [hoverPoint, setHoverPoint] = useState<{ x: number; y: number; value: number } | null>(null);
  const stroke = alert ? "#ef5f54" : "#31d38f";
  const safeValues = values.length ? values.slice(-13) : [0];
  const maxValue = Math.max(...safeValues, 1);
  const points = safeValues.map((value, index) => ({
    x: safeValues.length === 1 ? 45 : 2 + index * (86 / (safeValues.length - 1)),
    y: 24 - (value / maxValue) * 20,
    value,
  }));
  const path = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  return (
    <div className="relative">
      <svg viewBox="0 0 90 28" className="h-7 w-24 overflow-visible" aria-label={`${label} sparkline`}>
        <path d={path} fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
        {points.map((point, index) => (
          <circle
            key={index}
            cx={point.x}
            cy={point.y}
            r={hoverPoint?.x === point.x ? 3.2 : 2.2}
            fill={hoverPoint?.x === point.x ? "#f6e7c8" : stroke}
            className="cursor-crosshair"
            onMouseEnter={() => setHoverPoint(point)}
            onMouseLeave={() => setHoverPoint(null)}
          />
        ))}
      </svg>
      {hoverPoint && (
        <div
          className="pointer-events-none absolute z-20 min-w-28 rounded-lg border border-signal-copper/35 bg-[#081816]/95 px-3 py-2 text-[11px] shadow-2xl"
          style={{
            left: `${(hoverPoint.x / 90) * 100}%`,
            top: `${hoverPoint.y - 28}px`,
            transform: hoverPoint.x > 55 ? "translateX(-105%)" : "translateX(8px)",
          }}
        >
          <p className="font-mono text-signal-copper">{label}</p>
          <p className="font-mono text-foreground">{alert ? formatMinutes(hoverPoint.value) : formatThroughput(hoverPoint.value)}</p>
        </div>
      )}
    </div>
  );
}

function formatThroughput(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "n/a";
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K/min`;
  return `${value.toFixed(0)}/min`;
}

function formatMinutes(seconds: number | null | undefined) {
  if (seconds == null || Number.isNaN(seconds)) return "n/a";
  return `${(seconds / 60).toFixed(1)} min`;
}

export function PipelineHealthCard() {
  const { data } = useSWR<PipelineHealthResponse>("/api/pipeline/health", fetcher, { refreshInterval: 30000 });
  const stages = data?.stages?.length ? data.stages : [
    { name: "Ingestion", state: "Loading", healthy: true },
    { name: "Processing", state: "Loading", healthy: true },
    { name: "Sentiment", state: "Loading", healthy: true },
    { name: "Topics", state: "Loading", healthy: true },
    { name: "Storage", state: "Loading", healthy: true },
  ];
  const storage = data?.storage;
  const throughput = storage?.throughput_items_per_minute;
  const storageLatency = storage?.p95_latency_seconds ?? storage?.avg_latency_seconds;
  const latency = storageLatency ?? storage?.latest_lag_seconds;
  const latencyLabel = storageLatency == null && storage?.latest_lag_seconds != null ? "Lag" : "Latency";
  const latencySparkline = storage?.sparkline_latency_seconds?.length
    ? storage.sparkline_latency_seconds
    : storage?.latest_lag_seconds != null
      ? [storage.latest_lag_seconds]
      : [];
  const storageDetail = data?.provenance?.detail ?? (storage?.latest_storage_timestamp ? `Latest storage ${storage.latest_storage_timestamp.slice(0, 16).replace("T", " ")}` : "Waiting for batch metadata.");

  return (
    <section className="command-panel p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="command-label">Pipeline</p>
          <h3 className="mt-1 text-[14px] font-semibold tracking-[-0.012em] text-foreground">Operational health</h3>
        </div>
        <GitBranch className="size-4 text-signal-copper" aria-hidden="true" />
      </div>

      <div className="mt-4 grid grid-cols-[repeat(5,minmax(0,1fr))] items-start gap-1">
        {stages.map((stage, index) => {
          const Icon = STAGE_ICONS[stage.name as keyof typeof STAGE_ICONS] ?? CircleDot;
          const alert = !stage.healthy;
          return (
            <div key={stage.name} className="relative flex flex-col items-center gap-1 text-center">
              {index < stages.length - 1 && <div className="absolute left-[58%] right-[-42%] top-4 h-px bg-border" />}
              <div className={`relative z-10 grid size-8 place-items-center rounded-full border ${alert ? "border-signal-red/45 bg-signal-red/10 text-signal-red" : "border-signal-green/45 bg-signal-green/10 text-signal-green"}`}>
                <Icon className="size-4" aria-hidden="true" />
              </div>
              <p className="text-[10px] font-medium text-foreground">{stage.name}</p>
              <p className={`font-mono text-[10px] ${alert ? "text-signal-red" : "text-signal-green"}`}>{stage.state}</p>
            </div>
          );
        })}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-3">
        <div>
          <p className="text-[10px] uppercase text-muted-foreground">Throughput</p>
          <div className="mt-1 flex items-end justify-between gap-2">
            <div>
              <p className="font-mono text-lg font-semibold text-foreground">{formatThroughput(throughput).replace("/min", "")}</p>
              <p className="font-mono text-[10px] text-muted-foreground">items/min</p>
            </div>
            <Sparkline label="Throughput" values={storage?.sparkline_throughput_items_per_minute ?? []} />
          </div>
        </div>
        <div className="border-l border-border pl-3">
          <p className="text-[10px] uppercase text-muted-foreground">{latencyLabel}</p>
          <div className="mt-1 flex items-end justify-between gap-2">
            <div>
              <p className="font-mono text-lg font-semibold text-foreground">{latency == null ? "n/a" : (latency / 60).toFixed(1)}</p>
              <p className="font-mono text-[10px] text-muted-foreground">min</p>
            </div>
            <Sparkline alert label={latencyLabel} values={latencySparkline} />
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2 rounded-md border border-signal-copper/20 bg-signal-copper/8 px-3 py-2 text-[11px] text-muted-foreground">
        <MessageSquareText className="size-3.5 text-signal-copper" aria-hidden="true" />
        {storageDetail}
      </div>
    </section>
  );
}
