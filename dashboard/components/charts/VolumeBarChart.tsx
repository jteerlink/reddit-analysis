"use client";

import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { CHART_AXIS_PROPS, CHART_COLORS, CHART_GRID_PROPS, CHART_LEGEND_PROPS, CHART_SERIES_COLORS, CHART_TOOLTIP_PROPS } from "@/components/charts/chartTooltip";
import type { VolumeDaily } from "@/lib/types";

interface Props {
  data: VolumeDaily[];
}

export function VolumeBarChart({ data }: Props) {
  const subreddits = [...new Set(data.map((d) => d.subreddit))];
  const byDate: Record<string, Record<string, string | number>> = {};
  for (const row of data) {
    if (!byDate[row.date]) byDate[row.date] = { date: row.date };
    byDate[row.date][row.subreddit] = row.count;
  }
  const chartData = Object.values(byDate).sort((a, b) => (a.date > b.date ? 1 : -1));

  return (
    <div className="signal-chart-frame">
      <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis dataKey="date" {...CHART_AXIS_PROPS} tickFormatter={(v) => v.slice(5)} />
        <YAxis {...CHART_AXIS_PROPS} width={40} />
        <Tooltip {...CHART_TOOLTIP_PROPS} />
        <Legend {...CHART_LEGEND_PROPS} />
        {subreddits.map((s, i) => (
          <Bar key={s} dataKey={s} stackId="a" fill={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]} radius={[3, 3, 0, 0]} isAnimationActive={false} activeBar={{ stroke: CHART_COLORS.cursor, strokeWidth: 1 }} />
        ))}
      </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
