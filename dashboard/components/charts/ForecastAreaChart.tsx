"use client";

import { Fragment, useId } from "react";
import { AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { CHART_AXIS_PROPS, CHART_COLORS, CHART_GRID_PROPS, CHART_LEGEND_PROPS, CHART_SERIES_COLORS, CHART_TOOLTIP_PROPS } from "@/components/charts/chartTooltip";
import type { Forecast } from "@/lib/types";

interface Props {
  data: Forecast[];
  seriesLabels?: Record<string, string>;
}

interface ForecastBucket {
  yhatTotal: number;
  lowerTotal: number;
  upperTotal: number;
  count: number;
}

export function ForecastAreaChart({ data, seriesLabels = {} }: Props) {
  const chartId = useId().replace(/:/g, "");
  const series = [...new Set(data.map((d) => seriesLabels[d.subreddit] ?? d.subreddit))];
  const byDate: Record<string, Record<string, string | number | number[]>> = {};
  const buckets = new Map<string, ForecastBucket>();
  for (const row of data) {
    const label = seriesLabels[row.subreddit] ?? row.subreddit;
    const key = `${row.date}:${label}`;
    const bucket = buckets.get(key) ?? { yhatTotal: 0, lowerTotal: 0, upperTotal: 0, count: 0 };
    bucket.yhatTotal += row.yhat;
    bucket.lowerTotal += row.yhat_lower;
    bucket.upperTotal += row.yhat_upper;
    bucket.count += 1;
    buckets.set(key, bucket);
  }

  for (const [key, bucket] of buckets) {
    const [date, label] = key.split(":");
    if (!byDate[date]) byDate[date] = { date };
    byDate[date][`${label}_yhat`] = bucket.yhatTotal / bucket.count;
    byDate[date][`${label}_ci`] = [bucket.lowerTotal / bucket.count, bucket.upperTotal / bucket.count];
  }
  const chartData = Object.values(byDate).sort((a, b) => (a.date > b.date ? 1 : -1));

  return (
    <div className="signal-chart-frame">
      <ResponsiveContainer width="100%" height={420}>
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
        <YAxis domain={["auto", "auto"]} {...CHART_AXIS_PROPS} width={36} />
        <Tooltip {...CHART_TOOLTIP_PROPS} />
        <Legend {...CHART_LEGEND_PROPS} />
        {series.map((s) => (
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
        {series.map((s, i) => (
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
