"use client";

import { useState } from "react";
import { CheckCircle2, CircleDot, Database, GitBranch, MessageSquareText, Server, Workflow } from "lucide-react";

const STAGES = [
  { name: "Ingestion", state: "Healthy", icon: CircleDot },
  { name: "Processing", state: "Healthy", icon: Workflow },
  { name: "Sentiment", state: "Healthy", icon: CheckCircle2 },
  { name: "Topics", state: "Healthy", icon: Database },
  { name: "Storage", state: "Lag 2m", icon: Server, alert: true },
];

const SPARKLINE_VALUES = [17, 12, 18, 8, 14, 11, 19, 10, 13, 9, 18, 15, 20];

function Sparkline({ alert = false, label }: { alert?: boolean; label: string }) {
  const [hoverPoint, setHoverPoint] = useState<{ x: number; y: number; value: number } | null>(null);
  const stroke = alert ? "#ef5f54" : "#31d38f";
  const points = SPARKLINE_VALUES.map((value, index) => ({
    x: 2 + index * 7.15,
    y: 24 - value,
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
          <p className="font-mono text-foreground">{alert ? `${(hoverPoint.value / 10).toFixed(1)} min` : `${hoverPoint.value.toFixed(1)}K/min`}</p>
        </div>
      )}
    </div>
  );
}

export function PipelineHealthCard() {
  return (
    <section className="command-panel p-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="command-label">Pipeline</p>
          <h3 className="mt-1 text-sm font-semibold text-foreground">Operational health</h3>
        </div>
        <GitBranch className="size-4 text-signal-copper" aria-hidden="true" />
      </div>

      <div className="mt-4 grid grid-cols-[repeat(5,minmax(0,1fr))] items-start gap-1">
        {STAGES.map((stage, index) => {
          const Icon = stage.icon;
          return (
            <div key={stage.name} className="relative flex flex-col items-center gap-1 text-center">
              {index < STAGES.length - 1 && <div className="absolute left-[58%] right-[-42%] top-4 h-px bg-border" />}
              <div className={`relative z-10 grid size-8 place-items-center rounded-full border ${stage.alert ? "border-signal-red/45 bg-signal-red/10 text-signal-red" : "border-signal-green/45 bg-signal-green/10 text-signal-green"}`}>
                <Icon className="size-4" aria-hidden="true" />
              </div>
              <p className="text-[10px] font-medium text-foreground">{stage.name}</p>
              <p className={`font-mono text-[10px] ${stage.alert ? "text-signal-red" : "text-signal-green"}`}>{stage.state}</p>
            </div>
          );
        })}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-3">
        <div>
          <p className="text-[10px] uppercase text-muted-foreground">Throughput</p>
          <div className="mt-1 flex items-end justify-between gap-2">
            <div>
              <p className="font-mono text-lg font-semibold text-foreground">18.7K</p>
              <p className="font-mono text-[10px] text-muted-foreground">items/min</p>
            </div>
            <Sparkline label="Throughput" />
          </div>
        </div>
        <div className="border-l border-border pl-3">
          <p className="text-[10px] uppercase text-muted-foreground">Latency</p>
          <div className="mt-1 flex items-end justify-between gap-2">
            <div>
              <p className="font-mono text-lg font-semibold text-foreground">2.1</p>
              <p className="font-mono text-[10px] text-muted-foreground">min</p>
            </div>
            <Sparkline alert label="Latency" />
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2 rounded-md border border-signal-copper/20 bg-signal-copper/8 px-3 py-2 text-[11px] text-muted-foreground">
        <MessageSquareText className="size-3.5 text-signal-copper" aria-hidden="true" />
        Forecast export queued after topic refresh.
      </div>
    </section>
  );
}
