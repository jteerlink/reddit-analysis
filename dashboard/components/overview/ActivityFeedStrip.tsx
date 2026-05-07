"use client";

import useSWR from "swr";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, TriangleAlert } from "lucide-react";
import type { ActivityEvent } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

const TONE_CLASS = {
  warn: "text-signal-yellow border-signal-yellow/30 bg-signal-yellow/10",
  neutral: "text-muted-foreground border-white/20 bg-white/5",
  alert: "text-signal-red border-signal-red/30 bg-signal-red/10",
  good: "text-signal-green border-signal-green/30 bg-signal-green/10",
};

const SEVERITY_ICON = {
  info: Clock3,
  warn: AlertTriangle,
  error: TriangleAlert,
  success: CheckCircle2,
};

const SEVERITY_TONE = {
  info: "neutral",
  warn: "warn",
  error: "alert",
  success: "good",
} as const;

function displayTime(value: string) {
  if (!value) return "pending";
  return value.includes("T") ? value.slice(0, 16).replace("T", " ") : value;
}

export function ActivityFeedStrip() {
  const { data = [] } = useSWR<ActivityEvent[]>("/api/analysis/activity", fetcher);
  const events = data.slice(0, 4);

  return (
    <section className="command-panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-foreground">Activity feed</h3>
        <button className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground">
          View all
          <ArrowRight className="size-3" aria-hidden="true" />
        </button>
      </div>
      <div className="grid divide-y divide-border md:grid-cols-4 md:divide-x md:divide-y-0">
        {events.length ? events.map((event, index) => {
          const Icon = SEVERITY_ICON[event.severity] ?? Clock3;
          const tone = SEVERITY_TONE[event.severity] ?? "neutral";
          const key = event.source_ids[0] ?? `${event.timestamp}:${event.type}:${event.title}:${index}`;
          return (
            <article key={key} className="flex min-h-24 gap-3 px-4 py-3">
              <div className={`mt-1 grid size-6 shrink-0 place-items-center rounded-full border ${TONE_CLASS[tone]}`}>
                <Icon className="size-3.5" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <p className="font-mono text-[10px] text-muted-foreground">{displayTime(event.timestamp)}</p>
                <div className="mt-1 flex min-w-0 items-center gap-1.5">
                  <p className="truncate text-xs font-semibold text-foreground">{event.title}</p>
                  {event.state && event.state !== "ready" && (
                    <span className="shrink-0 rounded border border-signal-yellow/25 bg-signal-yellow/10 px-1.5 py-0.5 font-mono text-[9px] text-signal-yellow">
                      {event.state.replace("_", " ")}
                    </span>
                  )}
                </div>
                <p className="mt-1 truncate text-[11px] text-muted-foreground">{event.detail}</p>
                {event.provenance?.label && (
                  <p className="mt-1 truncate font-mono text-[9px] text-muted-foreground">{event.provenance.label.replace("_", " ")}</p>
                )}
              </div>
            </article>
          );
        }) : (
          <div className="col-span-4 grid min-h-24 place-items-center px-4 py-3 text-xs text-muted-foreground">
            Run analysis artifacts to populate activity
          </div>
        )}
      </div>
    </section>
  );
}
