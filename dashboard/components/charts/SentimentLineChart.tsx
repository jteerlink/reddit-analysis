"use client";

import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ReferenceLine, ResponsiveContainer,
} from "recharts";
import type { SentimentDaily, ChangePoint } from "@/lib/types";

type MAMode = "none" | "7d" | "30d" | "both";

interface Props {
  data: SentimentDaily[];
  changePoints: ChangePoint[];
  maMode: MAMode;
}

const SUB_COLORS = ["#F59E0B", "#60A5FA", "#34D399", "#F87171", "#A78BFA"];

export function SentimentLineChart({ data, changePoints, maMode }: Props) {
  const subreddits = [...new Set(data.map((d) => d.subreddit))];
  const byDate: Record<string, Record<string, string | number | null>> = {};
  for (const row of data) {
    if (!byDate[row.date]) byDate[row.date] = { date: row.date };
    byDate[row.date][`${row.subreddit}_score`] = row.mean_score;
    if (row.rolling_7d != null) byDate[row.date][`${row.subreddit}_7d`] = row.rolling_7d;
    if (row.rolling_30d != null) byDate[row.date][`${row.subreddit}_30d`] = row.rolling_30d;
  }
  const chartData = Object.values(byDate).sort((a, b) => String(a.date) > String(b.date) ? 1 : -1);

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
        <YAxis domain={[-1, 1]} tick={{ fontSize: 10 }} width={36} />
        <Tooltip contentStyle={{ background: "#141619", border: "1px solid #2d2f33", fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {changePoints.map((cp) => (
          <ReferenceLine key={`${cp.subreddit}-${cp.date}`} x={cp.date} stroke={cp.magnitude > 0 ? "#34D399" : "#F87171"} strokeDasharray="4 2" />
        ))}
        {subreddits.map((s, i) => (
          <Line key={s} dataKey={`${s}_score`} name={s} stroke={SUB_COLORS[i % SUB_COLORS.length]} dot={false} strokeWidth={1.5} />
        ))}
        {(maMode === "7d" || maMode === "both") &&
          subreddits.map((s, i) => (
            <Line key={`${s}_7d`} dataKey={`${s}_7d`} name={`${s} 7d`} stroke={SUB_COLORS[i % SUB_COLORS.length]} dot={false} strokeDasharray="4 2" strokeWidth={1} />
          ))}
        {(maMode === "30d" || maMode === "both") &&
          subreddits.map((s, i) => (
            <Line key={`${s}_30d`} dataKey={`${s}_30d`} name={`${s} 30d`} stroke={SUB_COLORS[i % SUB_COLORS.length]} dot={false} strokeDasharray="8 4" strokeWidth={1} />
          ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
