"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { VolumeDaily } from "@/lib/types";

interface Props {
  data: VolumeDaily[];
}

const COLORS = ["#F59E0B", "#34D399", "#60A5FA", "#F87171", "#A78BFA", "#FB923C"];

export function VolumeBarChart({ data }: Props) {
  const subreddits = [...new Set(data.map((d) => d.subreddit))];
  const byDate: Record<string, Record<string, string | number>> = {};
  for (const row of data) {
    if (!byDate[row.date]) byDate[row.date] = { date: row.date };
    byDate[row.date][row.subreddit] = row.count;
  }
  const chartData = Object.values(byDate).sort((a, b) => (a.date > b.date ? 1 : -1));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
        <YAxis tick={{ fontSize: 10 }} width={40} />
        <Tooltip contentStyle={{ background: "#141619", border: "1px solid #2d2f33", fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {subreddits.map((s, i) => (
          <Bar key={s} dataKey={s} stackId="a" fill={COLORS[i % COLORS.length]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
