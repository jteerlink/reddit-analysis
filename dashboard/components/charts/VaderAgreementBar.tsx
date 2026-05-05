"use client";

import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from "recharts";
import { CHART_AXIS_PROPS, CHART_COLORS, CHART_GRID_PROPS, CHART_TOOLTIP_PROPS } from "@/components/charts/chartTooltip";
import type { VaderAgreement } from "@/lib/types";

interface Props {
  data: VaderAgreement[];
}

function rateColor(rate: number): string {
  if (rate >= 0.8) return CHART_COLORS.green;
  if (rate >= 0.6) return CHART_COLORS.copper;
  return CHART_COLORS.red;
}

export function VaderAgreementBar({ data }: Props) {
  const sorted = [...data].sort((a, b) => b.agreement_rate - a.agreement_rate);
  return (
    <div className="signal-chart-frame">
      <ResponsiveContainer width="100%" height={Math.max(160, sorted.length * 28)}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 8, right: 8, bottom: 0, left: 80 }}>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis type="number" domain={[0, 1]} {...CHART_AXIS_PROPS} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
        <YAxis type="category" dataKey="subreddit" {...CHART_AXIS_PROPS} width={80} />
        <Tooltip
          formatter={(v) => typeof v === "number" ? `${Math.round(v * 100)}%` : v}
          {...CHART_TOOLTIP_PROPS}
        />
        <Bar dataKey="agreement_rate" name="Agreement" isAnimationActive={false}>
          {sorted.map((entry) => (
            <Cell key={entry.subreddit} fill={rateColor(entry.agreement_rate)} />
          ))}
        </Bar>
      </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
