"use client";

import { AreaChart, Area, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { Forecast } from "@/lib/types";

interface Props {
  data: Forecast[];
}

const SUB_COLORS = ["#F59E0B", "#60A5FA", "#34D399", "#F87171"];

export function ForecastAreaChart({ data }: Props) {
  const subreddits = [...new Set(data.map((d) => d.subreddit))];
  const byDate: Record<string, Record<string, string | number | number[]>> = {};
  for (const row of data) {
    if (!byDate[row.date]) byDate[row.date] = { date: row.date };
    byDate[row.date][`${row.subreddit}_yhat`] = row.yhat;
    byDate[row.date][`${row.subreddit}_ci`] = [row.yhat_lower, row.yhat_upper];
  }
  const chartData = Object.values(byDate).sort((a, b) => (a.date > b.date ? 1 : -1));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
        <YAxis domain={[-1, 1]} tick={{ fontSize: 10 }} width={36} />
        <Tooltip contentStyle={{ background: "#141619", border: "1px solid #2d2f33", fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {subreddits.map((s, i) => (
          <>
            <Area
              key={`${s}_ci`}
              dataKey={`${s}_ci`}
              name={`${s} 95% CI`}
              fill={SUB_COLORS[i % SUB_COLORS.length]}
              fillOpacity={0.15}
              stroke="none"
            />
            <Area
              key={`${s}_yhat`}
              dataKey={`${s}_yhat`}
              name={`${s} forecast`}
              stroke={SUB_COLORS[i % SUB_COLORS.length]}
              fill="none"
              strokeWidth={1.5}
            />
          </>
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
