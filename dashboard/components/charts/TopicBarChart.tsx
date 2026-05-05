"use client";

import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { CHART_AXIS_PROPS, CHART_COLORS, CHART_GRID_PROPS, CHART_TOOLTIP_PROPS } from "@/components/charts/chartTooltip";
import type { TopicOverTime } from "@/lib/types";

interface Props {
  data: TopicOverTime[];
}

export function TopicBarChart({ data }: Props) {
  return (
    <div className="signal-chart-frame">
      <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis dataKey="week_start" {...CHART_AXIS_PROPS} tickFormatter={(v) => v.slice(5)} />
        <YAxis {...CHART_AXIS_PROPS} width={40} />
        <Tooltip {...CHART_TOOLTIP_PROPS} />
        <Bar dataKey="doc_count" fill={CHART_COLORS.copper} radius={[4, 4, 1, 1]} name="Docs" isAnimationActive={false} activeBar={{ stroke: CHART_COLORS.cursor, strokeWidth: 1 }} />
      </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
