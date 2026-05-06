import type { TopicHeatmapRow } from "@/lib/types";

function tone(value: number | null) {
  if (value === null || Number.isNaN(value)) return "bg-muted text-muted-foreground";
  if (value > 0.35) return "bg-emerald-500/70 text-emerald-950";
  if (value > 0.1) return "bg-emerald-500/35 text-emerald-100";
  if (value < -0.35) return "bg-red-500/70 text-red-950";
  if (value < -0.1) return "bg-red-500/35 text-red-100";
  return "bg-slate-500/20 text-slate-200";
}

export function TopicHeatmap({ data }: { data: TopicHeatmapRow[] }) {
  const weeks = Array.from(new Set(data.map((row) => row.week_start))).sort().slice(-12);
  const topics = Array.from(new Set(data.map((row) => row.topic_id))).slice(0, 18);
  const values = new Map(data.map((row) => [`${row.topic_id}:${row.week_start}`, row.avg_sentiment]));

  if (!weeks.length || !topics.length) {
    return <div className="grid h-48 place-items-center text-sm text-muted-foreground">No topic sentiment rows</div>;
  }

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[680px]">
        <div className="grid gap-1" style={{ gridTemplateColumns: `84px repeat(${weeks.length}, minmax(42px, 1fr))` }}>
          <div />
          {weeks.map((week) => (
            <div key={week} className="truncate text-center font-mono text-[10px] text-muted-foreground">
              {week.slice(5)}
            </div>
          ))}
          {topics.map((topic) => (
            <div key={topic} className="contents">
              <div className="truncate pr-2 text-right font-mono text-[11px] text-muted-foreground">#{topic}</div>
              {weeks.map((week) => {
                const value = values.get(`${topic}:${week}`) ?? null;
                return (
                  <div
                    key={`${topic}:${week}`}
                    title={`Topic ${topic} / ${week}: ${value === null ? "n/a" : value.toFixed(3)}`}
                    className={`grid h-7 place-items-center rounded-sm font-mono text-[10px] tabular-nums ${tone(value)}`}
                  >
                    {value === null ? "-" : value.toFixed(1)}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
