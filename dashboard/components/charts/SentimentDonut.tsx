"use client";

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";
import type { SentimentSummary } from "@/lib/types";

interface Props {
  data: SentimentSummary[];
}

const COLORS: Record<string, string> = {
  positive: "#34D399",
  neutral: "#94A3B8",
  negative: "#F87171",
};

export function SentimentDonut({ data }: Props) {
  const total = data.reduce((s, d) => s + d.count, 0);
  const entries = data.map((d) => ({
    name: d.label,
    value: d.count,
    pct: total ? Math.round((d.count / total) * 100) : 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={entries}
          dataKey="value"
          nameKey="name"
          innerRadius={55}
          outerRadius={80}
          paddingAngle={2}
          isAnimationActive={false}
        >
          {entries.map((e) => (
            <Cell key={e.name} fill={COLORS[e.name] ?? "#6B7280"} />
          ))}
        </Pie>
        <Tooltip
          formatter={(value, name) => [`${value} (${entries.find((e) => e.name === name)?.pct}%)`, name]}
          contentStyle={{ background: "#141619", border: "1px solid #2d2f33", fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
