"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, TriangleAlert } from "lucide-react";

const EVENTS = [
  { time: "2m ago", title: "Ingestion spike", detail: "r/technology 18.2K items", tone: "warn", icon: AlertTriangle },
  { time: "6m ago", title: "Pipeline lag", detail: "Topics 2m delay", tone: "neutral", icon: Clock3 },
  { time: "16m ago", title: "Model drift warning", detail: "Sentiment drift 0.08", tone: "alert", icon: TriangleAlert },
  { time: "45m ago", title: "Deploy: v2.3.1", detail: "Model success", tone: "good", icon: CheckCircle2 },
];

const TONE_CLASS = {
  warn: "text-signal-yellow border-signal-yellow/30 bg-signal-yellow/10",
  neutral: "text-muted-foreground border-white/20 bg-white/5",
  alert: "text-signal-red border-signal-red/30 bg-signal-red/10",
  good: "text-signal-green border-signal-green/30 bg-signal-green/10",
};

export function ActivityFeedStrip() {
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
        {EVENTS.map((event) => {
          const Icon = event.icon;
          return (
            <article key={event.title} className="flex min-h-24 gap-3 px-4 py-3">
              <div className={`mt-1 grid size-6 shrink-0 place-items-center rounded-full border ${TONE_CLASS[event.tone as keyof typeof TONE_CLASS]}`}>
                <Icon className="size-3.5" aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <p className="font-mono text-[10px] text-muted-foreground">{event.time}</p>
                <p className="mt-1 truncate text-xs font-semibold text-foreground">{event.title}</p>
                <p className="mt-1 truncate text-[11px] text-muted-foreground">{event.detail}</p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
