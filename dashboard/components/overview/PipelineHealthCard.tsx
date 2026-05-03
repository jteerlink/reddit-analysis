"use client";

import { CheckCircle2, CircleDot, Database, GitBranch, MessageSquareText, Server, Workflow } from "lucide-react";

const STAGES = [
  { name: "Ingestion", state: "Healthy", icon: CircleDot },
  { name: "Processing", state: "Healthy", icon: Workflow },
  { name: "Sentiment", state: "Healthy", icon: CheckCircle2 },
  { name: "Topics", state: "Healthy", icon: Database },
  { name: "Storage", state: "Lag 2m", icon: Server, alert: true },
];

function Sparkline({ alert = false }: { alert?: boolean }) {
  const stroke = alert ? "#ef5f54" : "#31d38f";
  return (
    <svg viewBox="0 0 90 28" className="h-7 w-24" aria-hidden="true">
      <path d="M2 17 L9 12 L16 18 L23 8 L30 14 L37 11 L44 19 L51 10 L58 13 L65 9 L72 18 L80 15 L88 20" fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
    </svg>
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
            <Sparkline />
          </div>
        </div>
        <div className="border-l border-border pl-3">
          <p className="text-[10px] uppercase text-muted-foreground">Latency</p>
          <div className="mt-1 flex items-end justify-between gap-2">
            <div>
              <p className="font-mono text-lg font-semibold text-foreground">2.1</p>
              <p className="font-mono text-[10px] text-muted-foreground">min</p>
            </div>
            <Sparkline alert />
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
