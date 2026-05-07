"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { Badge } from "@/components/ui/badge";
import type { PipelineStep } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const STATE_BADGE: Record<string, { variant: "default" | "secondary" | "outline" | "destructive"; label: string }> = {
  done: { variant: "default", label: "Done" },
  idle: { variant: "secondary", label: "Ready" },
  locked: { variant: "outline", label: "Locked" },
  running: { variant: "secondary", label: "Running…" },
  error: { variant: "destructive", label: "Failed" },
};

export default function PipelinePage() {
  const { data: steps, mutate } = useSWR<PipelineStep[]>("/api/pipeline/status", fetcher, { refreshInterval: 5000 });
  const [output, setOutput] = useState<string[]>(["No runs yet. Select a step above to begin."]);
  const [running, setRunning] = useState(false);
  const terminalRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [output]);

  async function runStep(stepNum: number | "all") {
    if (running) return;
    setRunning(true);
    setOutput([`=== Starting ${stepNum === "all" ? "all steps" : `step ${stepNum}`} ===`]);

    const url = stepNum === "all" ? "/api/pipeline/run-all" : `/api/pipeline/run/${stepNum}`;
    try {
      const res = await fetch(url);
      if (!res.body) throw new Error("No response body");
      const reader = res.body.getReader();
      const dec = new TextDecoder("utf-8", { fatal: false });
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        const events = lines.filter((l) => l.startsWith("data: ")).map((l) => l.slice(6));
        if (events.length) setOutput((prev) => [...prev, ...events].slice(-300));
      }
      const remaining = dec.decode();
      if (remaining.startsWith("data: ")) setOutput((prev) => [...prev, remaining.slice(6)].slice(-300));
    } catch (e) {
      setOutput((prev) => [...prev, `[ERROR] ${e}`]);
    }
    setRunning(false);
    mutate();
  }

  const doneCount = steps?.filter((s) => s.done).length ?? 0;

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Operations" title="Pipeline runner" subtitle="Run each step in sequence to build the full ML pipeline." />

      {steps && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>{doneCount} / {steps.length} complete</span>
          <div className="flex gap-1">
            {steps.map((s) => (
              <div key={s.num} className={`w-3 h-3 rounded-full ${s.done ? "bg-emerald-500" : "bg-border"}`} title={s.name} />
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        {steps?.map((step) => {
          const badgeInfo = STATE_BADGE[running && !step.done && step.prereq_ok ? "running" : step.state] ?? STATE_BADGE.locked;
          return (
            <div key={step.num} className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <span className="text-xs text-muted-foreground w-6 shrink-0">#{step.num}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground">{step.name}</p>
                <p className="text-xs text-muted-foreground">{step.description}</p>
              </div>
              <Badge variant={badgeInfo.variant}>{badgeInfo.label}</Badge>
              <button
                disabled={running || !step.prereq_ok || step.done}
                onClick={() => runStep(step.num)}
                className="px-3 py-1 rounded text-xs bg-muted text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Run
              </button>
            </div>
          );
        })}
      </div>

      <button
        disabled={running}
        onClick={() => runStep("all")}
        className="px-4 py-2 rounded-lg bg-amber-500 text-black text-sm font-medium hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {running ? "Running…" : "Run all steps"}
      </button>

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex items-center gap-1.5 px-4 py-2 border-b border-border bg-muted/30">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
          <span className="ml-2 text-xs text-muted-foreground font-mono">Output</span>
        </div>
        <pre ref={terminalRef} className="p-4 text-xs font-mono text-emerald-400 h-72 overflow-y-auto whitespace-pre-wrap">
          {output.join("\n")}
        </pre>
      </div>
    </div>
  );
}
