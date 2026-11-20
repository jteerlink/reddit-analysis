"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { SectionHeader } from "@/components/layout/SectionHeader";
import { Badge } from "@/components/ui/badge";
import type { PipelineStep } from "@/lib/types";

async function fetchStatus(url: string) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Pipeline status returned HTTP ${response.status}`);
  return {
    steps: await response.json() as PipelineStep[],
    localOperator: response.headers.get("X-Pipeline-Local-Operator") === "true",
  };
}

const STATE_BADGE: Record<string, { variant: "default" | "secondary" | "outline" | "destructive"; label: string }> = {
  done: { variant: "default", label: "Done" },
  idle: { variant: "secondary", label: "Ready" },
  locked: { variant: "outline", label: "Locked" },
  running: { variant: "secondary", label: "Running…" },
  error: { variant: "destructive", label: "Failed" },
};

export default function PipelinePage() {
  const { data, error, mutate } = useSWR("/api/pipeline/status", fetchStatus, { refreshInterval: 5000 });
  const steps = data?.steps;
  const [output, setOutput] = useState<string[]>(["No runs yet. Select a step above to begin."]);
  const [runningStep, setRunningStep] = useState<number | "all" | null>(null);
  const [operatorToken, setOperatorToken] = useState("");
  const canRun = data?.localOperator || Boolean(operatorToken);
  const terminalRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [output]);

  async function runStep(stepNum: number | "all", rebuild = false) {
    if (runningStep !== null) return;
    setRunningStep(stepNum);
    setOutput([`=== Starting ${stepNum === "all" ? "all steps" : `step ${stepNum}`} ===`]);

    const url = stepNum === "all" ? `/api/pipeline/run-all?rebuild=${rebuild}` : `/api/pipeline/run/${stepNum}`;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: operatorToken && !data?.localOperator ? { Authorization: `Bearer ${operatorToken}` } : undefined,
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail ?? `HTTP ${res.status}`);
      }
      if (!res.body) throw new Error("No response body");
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buffer = "";
      let terminal = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += dec.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const lines = frame.split("\n");
          const event = lines.find((line) => line.startsWith("event: "))?.slice(7);
          const data = lines.filter((line) => line.startsWith("data: ")).map((line) => line.slice(6));
          if (event === "result" || event === "busy") terminal = true;
          const output = event === "result" ? [`Pipeline ${data.join(" ")}.`] : data;
          if (output.length) setOutput((previous) => [...previous, ...output].slice(-300));
        }
      }
      if (!terminal) throw new Error("Run interrupted before a result was received");
    } catch (e) {
      setOutput((prev) => [...prev, `[ERROR] ${e}`]);
    }
    setRunningStep(null);
    mutate();
  }

  const doneCount = steps?.filter((s) => s.done).length ?? 0;

  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="Operations" title="Pipeline runner" subtitle="Run each step in sequence to build the full ML pipeline." />

      {(data || error) && !data?.localOperator && (
        <label className="block text-sm">
          Operator token
          <input type="password" autoComplete="off" value={operatorToken}
            onChange={(event) => setOperatorToken(event.target.value)}
            className="ml-3 rounded border border-border bg-card px-2 py-1" />
        </label>
      )}

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
          const isRunning = runningStep === "all" || runningStep === step.num;
          const badgeInfo = STATE_BADGE[isRunning ? "running" : step.state] ?? STATE_BADGE.locked;
          return (
            <div key={step.num} className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3">
              <span className="text-xs text-muted-foreground w-6 shrink-0">#{step.num}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-foreground">{step.name}</p>
                <p className="text-xs text-muted-foreground">{step.description}</p>
              </div>
              <Badge variant={badgeInfo.variant}>{badgeInfo.label}</Badge>
              <button
                disabled={!canRun || runningStep !== null || !step.prereq_ok}
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
        disabled={!canRun || runningStep !== null}
        onClick={() => runStep("all")}
        className="px-4 py-2 rounded-lg bg-amber-500 text-black text-sm font-medium hover:bg-amber-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {runningStep !== null ? "Running…" : "Refresh pipeline"}
      </button>

      <button type="button" disabled={!canRun || runningStep !== null}
        onClick={() => runStep("all", true)}
        className="ml-2 rounded border border-border px-4 py-2 text-sm disabled:opacity-40">
        Rebuild pipeline
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
