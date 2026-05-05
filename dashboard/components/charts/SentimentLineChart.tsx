"use client";

import { useId } from "react";
import {
  LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend,
  ReferenceLine, ResponsiveContainer,
} from "recharts";
import { CHART_AXIS_PROPS, CHART_COLORS, CHART_GRID_PROPS, CHART_LEGEND_PROPS, CHART_SERIES_COLORS, CHART_TOOLTIP_PROPS } from "@/components/charts/chartTooltip";
import type { SentimentDaily, ChangePoint } from "@/lib/types";

type MAMode = "none" | "7d" | "30d" | "both";

interface Props {
  data: SentimentDaily[];
  changePoints: ChangePoint[];
  maMode: MAMode;
}

export function SentimentLineChart({ data, changePoints, maMode }: Props) {
  const chartId = useId().replace(/:/g, "");
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
    <div className="signal-chart-frame">
      <ResponsiveContainer width="100%" height={260}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={`${chartId}-streamGlow`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor={CHART_COLORS.green} stopOpacity="0.2" />
            <stop offset="50%" stopColor={CHART_COLORS.copper} stopOpacity="0.28" />
            <stop offset="100%" stopColor={CHART_COLORS.red} stopOpacity="0.2" />
          </linearGradient>
          <filter id={`${chartId}-softGlow`}>
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <CartesianGrid {...CHART_GRID_PROPS} />
        <XAxis dataKey="date" {...CHART_AXIS_PROPS} tickFormatter={(v) => v.slice(5)} />
        <YAxis domain={[-1, 1]} {...CHART_AXIS_PROPS} width={36} />
        <Tooltip {...CHART_TOOLTIP_PROPS} />
        <Legend {...CHART_LEGEND_PROPS} />
        {changePoints.map((cp) => (
          <ReferenceLine key={`${cp.subreddit}-${cp.date}`} x={cp.date} stroke={cp.magnitude > 0 ? CHART_COLORS.green : CHART_COLORS.red} strokeDasharray="4 2" />
        ))}
        {subreddits.map((s) => (
          <Line
            key={`${s}_stream`}
            dataKey={`${s}_score`}
            name={`${s} signal band`}
            stroke={`url(#${chartId}-streamGlow)`}
            dot={false}
            activeDot={false}
            strokeWidth={18}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={0.22}
            legendType="none"
            isAnimationActive={false}
          />
        ))}
        {subreddits.map((s, i) => (
          <Line
            key={s}
            dataKey={`${s}_score`}
            name={s}
            stroke={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]}
            dot={false}
            activeDot={{ r: 5, stroke: CHART_COLORS.cursor, strokeWidth: 1.5 }}
            strokeWidth={2.4}
            strokeLinecap="round"
            strokeLinejoin="round"
            filter={`url(#${chartId}-softGlow)`}
            isAnimationActive={false}
          />
        ))}
        {(maMode === "7d" || maMode === "both") &&
          subreddits.map((s, i) => (
            <Line key={`${s}_7d`} dataKey={`${s}_7d`} name={`${s} 7d`} stroke={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]} dot={false} activeDot={{ r: 4, stroke: CHART_COLORS.cursor, strokeWidth: 1 }} strokeDasharray="4 2" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" opacity={0.82} isAnimationActive={false} />
          ))}
        {(maMode === "30d" || maMode === "both") &&
          subreddits.map((s, i) => (
            <Line key={`${s}_30d`} dataKey={`${s}_30d`} name={`${s} 30d`} stroke={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]} dot={false} activeDot={{ r: 4, stroke: CHART_COLORS.cursor, strokeWidth: 1 }} strokeDasharray="8 4" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" opacity={0.74} isAnimationActive={false} />
          ))}
      </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
