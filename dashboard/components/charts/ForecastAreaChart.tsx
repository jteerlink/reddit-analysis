"use client";

import { Fragment, useId } from "react";
import { AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { CHART_AXIS_PROPS, CHART_COLORS, CHART_GRID_PROPS, CHART_LEGEND_PROPS, CHART_SERIES_COLORS, CHART_TOOLTIP_PROPS } from "@/components/charts/chartTooltip";
import type { Forecast } from "@/lib/types";

interface Props {
  data: Forecast[];
}

export function ForecastAreaChart({ data }: Props) {
  const chartId = useId().replace(/:/g, "");
  const subreddits = [...new Set(data.map((d) => d.subreddit))];
  const byDate: Record<string, Record<string, string | number | number[]>> = {};
  for (const row of data) {
    if (!byDate[row.date]) byDate[row.date] = { date: row.date };
    byDate[row.date][`${row.subreddit}_yhat`] = row.yhat;
    byDate[row.date][`${row.subreddit}_ci`] = [row.yhat_lower, row.yhat_upper];
  }
  const chartData = Object.values(byDate).sort((a, b) => (a.date > b.date ? 1 : -1));

  return (
    <div className="signal-chart-frame">
      <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={`${chartId}-forecastGlow`} x1="0" x2="1" y1="0" y2="0">
            <stop offset="0%" stopColor={CHART_COLORS.green} stopOpacity="0.2" />
            <stop offset="52%" stopColor={CHART_COLORS.copper} stopOpacity="0.3" />
            <stop offset="100%" stopColor={CHART_COLORS.red} stopOpacity="0.18" />
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
        {subreddits.map((s) => (
          <Area
            key={`${s}_stream`}
            dataKey={`${s}_yhat`}
            name={`${s} signal band`}
            stroke={`url(#${chartId}-forecastGlow)`}
            fill="none"
            strokeWidth={18}
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity={0.2}
            legendType="none"
            activeDot={false}
            isAnimationActive={false}
          />
        ))}
        {subreddits.map((s, i) => (
          <Fragment key={s}>
            <Area
              dataKey={`${s}_ci`}
              name={`${s} 95% CI`}
              fill={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]}
              fillOpacity={0.15}
              stroke="none"
              isAnimationActive={false}
            />
            <Area
              dataKey={`${s}_yhat`}
              name={`${s} forecast`}
              stroke={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]}
              fill="none"
              strokeWidth={2.3}
              strokeLinecap="round"
              strokeLinejoin="round"
              filter={`url(#${chartId}-softGlow)`}
              activeDot={{ r: 5, stroke: CHART_COLORS.cursor, strokeWidth: 1.5 }}
              isAnimationActive={false}
            />
          </Fragment>
        ))}
      </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
