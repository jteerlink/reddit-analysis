"use client";

import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";
import { CHART_AXIS_PROPS, CHART_COLORS, CHART_GRID_PROPS, CHART_TOOLTIP_PROPS } from "@/components/charts/chartTooltip";
import type { Post } from "@/lib/types";

interface Props {
  data: Post[];
}

export function ConfidenceHistogram({ data }: Props) {
  const bins = Array.from({ length: 20 }, (_, i) => ({
    bin: (i / 20).toFixed(2),
    count: 0,
  }));
  for (const row of data) {
    const idx = Math.min(Math.floor(row.confidence * 20), 19);
    bins[idx].count++;
  }

  return (
    <div className="signal-chart-frame">
      <ResponsiveContainer width="100%" height={200}>
      <BarChart data={bins} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis dataKey="bin" {...CHART_AXIS_PROPS} />
        <YAxis {...CHART_AXIS_PROPS} width={40} />
        <Tooltip {...CHART_TOOLTIP_PROPS} />
        <ReferenceLine x="0.75" stroke={CHART_COLORS.copper} strokeDasharray="4 2" label={{ value: "0.75", fill: CHART_COLORS.copper, fontSize: 10 }} />
        <Bar dataKey="count" fill={CHART_COLORS.green} radius={[4, 4, 1, 1]} name="Count" isAnimationActive={false} activeBar={{ stroke: CHART_COLORS.cursor, strokeWidth: 1 }} />
      </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
