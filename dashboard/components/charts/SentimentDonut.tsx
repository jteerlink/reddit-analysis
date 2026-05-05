"use client";

import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { CHART_COLORS, CHART_LEGEND_PROPS, CHART_TOOLTIP_PROPS } from "@/components/charts/chartTooltip";
import type { SentimentSummary } from "@/lib/types";

interface Props {
  data: SentimentSummary[];
}

const COLORS: Record<string, string> = {
  positive: CHART_COLORS.green,
  neutral: CHART_COLORS.copper,
  negative: CHART_COLORS.red,
};

export function SentimentDonut({ data }: Props) {
  const total = data.reduce((s, d) => s + d.count, 0);
  const entries = data.map((d) => ({
    name: d.label,
    value: d.count,
    pct: total ? Math.round((d.count / total) * 100) : 0,
  }));

  return (
    <div className="signal-chart-frame">
      <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={entries}
          dataKey="value"
          nameKey="name"
          innerRadius={55}
          outerRadius={80}
          paddingAngle={2}
          stroke="rgba(255,255,255,0.08)"
          isAnimationActive={false}
        >
          {entries.map((e) => (
            <Cell key={e.name} fill={COLORS[e.name] ?? "#6B7280"} />
          ))}
        </Pie>
        <Tooltip
          formatter={(value, name) => [`${value} (${entries.find((e) => e.name === name)?.pct}%)`, name]}
          {...CHART_TOOLTIP_PROPS}
        />
        <Legend {...CHART_LEGEND_PROPS} />
      </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
