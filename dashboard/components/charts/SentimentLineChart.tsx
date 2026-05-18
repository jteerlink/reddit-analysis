"use client";

import React, { useState, useId } from "react";
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
  seriesLabels?: Record<string, string>;
}

const TOOLTIP_STYLE: React.CSSProperties = {
  background: "rgba(8, 24, 22, 0.96)",
  border: "1px solid rgba(192, 122, 69, 0.35)",
  borderRadius: 8,
  boxShadow: "0 18px 48px rgba(0,0,0,0.36)",
  padding: "10px 14px",
  fontFamily: "var(--font-geist-mono)",
  fontSize: 11,
  color: "#e9f4ee",
  minWidth: 160,
};

interface TEntry { name: string; value: unknown; color: string; }

function SentimentTooltip({ active, payload, label }: { active?: boolean; payload?: TEntry[]; label?: string }) {
  if (!active || !payload?.length) return null;
  const rows = payload.filter((e) => !e.name.endsWith(" signal band"));
  return (
    <div style={TOOLTIP_STYLE}>
      <div style={{ color: "#c07a45", marginBottom: 10 }}>{label}</div>
      {rows.map((e) => (
        <div key={e.name} style={{ display: "flex", justifyContent: "space-between", gap: 24, marginTop: 4 }}>
          <span style={{ color: e.color }}>{e.name}</span>
          <span style={{ color: "#e9f4ee" }}>{typeof e.value === "number" ? e.value.toFixed(3) : String(e.value ?? "")}</span>
        </div>
      ))}
    </div>
  );
}

interface Bucket {
  scoreTotal: number; count: number;
  rolling7dTotal: number; count7d: number;
  rolling30dTotal: number; count30d: number;
}

export function SentimentLineChart({ data, changePoints, maMode, seriesLabels = {} }: Props) {
  const chartId = useId().replace(/:/g, "");
  const [highlighted, setHighlighted] = useState<string | null>(null);

  const series = [...new Set(data.map((d) => seriesLabels[d.subreddit] ?? d.subreddit))];

  const buckets = new Map<string, Bucket>();
  for (const row of data) {
    const label = seriesLabels[row.subreddit] ?? row.subreddit;
    const key = `${row.date}\0${label}`;
    const b = buckets.get(key) ?? { scoreTotal: 0, count: 0, rolling7dTotal: 0, count7d: 0, rolling30dTotal: 0, count30d: 0 };
    b.scoreTotal += row.mean_score ?? 0;
    b.count += 1;
    if (row.rolling_7d != null) { b.rolling7dTotal += row.rolling_7d; b.count7d += 1; }
    if (row.rolling_30d != null) { b.rolling30dTotal += row.rolling_30d; b.count30d += 1; }
    buckets.set(key, b);
  }

  const byDate: Record<string, Record<string, string | number | null>> = {};
  for (const [key, b] of buckets) {
    const sep = key.indexOf("\0");
    const date = key.slice(0, sep);
    const label = key.slice(sep + 1);
    if (!byDate[date]) byDate[date] = { date };
    byDate[date][`${label}_score`] = b.scoreTotal / b.count;
    if (b.count7d > 0) byDate[date][`${label}_7d`] = b.rolling7dTotal / b.count7d;
    if (b.count30d > 0) byDate[date][`${label}_30d`] = b.rolling30dTotal / b.count30d;
  }
  const chartData = Object.values(byDate).sort((a, b) => String(a.date) > String(b.date) ? 1 : -1);

  const handleLegendClick = (entry: { value?: string }) => {
    const base = (entry.value ?? "").replace(/ (7d|30d)$/, "");
    setHighlighted((prev) => prev === base ? null : base);
  };

  const dim = (s: string) => !!(highlighted && highlighted !== s);
  const showingMovingAverage = maMode !== "none";
  const actualOpacity = (s: string) => dim(s) ? 0.1 : showingMovingAverage ? 0.28 : 1;
  const actualBandOpacity = (s: string) => dim(s) ? 0.03 : showingMovingAverage ? 0.08 : 0.22;

  return (
    <div className="signal-chart-frame">
      <ResponsiveContainer width="100%" height={420}>
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
        <YAxis domain={["auto", "auto"]} {...CHART_AXIS_PROPS} width={36} />
        <Tooltip
          content={<SentimentTooltip />}
          cursor={CHART_TOOLTIP_PROPS.cursor}
        />
        <Legend
          {...CHART_LEGEND_PROPS}
          onClick={handleLegendClick}
          wrapperStyle={{ ...CHART_LEGEND_PROPS.wrapperStyle, cursor: "pointer" }}
        />
        {changePoints.map((cp) => (
          <ReferenceLine key={`${cp.subreddit}-${cp.date}`} x={cp.date} stroke={cp.magnitude > 0 ? CHART_COLORS.green : CHART_COLORS.red} strokeDasharray="4 2" />
        ))}
        {series.map((s) => (
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
            opacity={actualBandOpacity(s)}
            legendType="none"
            isAnimationActive={false}
          />
        ))}
        {series.map((s, i) => (
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
            opacity={actualOpacity(s)}
            isAnimationActive={false}
          />
        ))}
        {(maMode === "7d" || maMode === "both") &&
          series.map((s, i) => (
            <Line key={`${s}_7d`} dataKey={`${s}_7d`} name={`${s} 7d`} stroke={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]} dot={false} activeDot={{ r: 4, stroke: CHART_COLORS.cursor, strokeWidth: 1 }} strokeDasharray="4 2" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" opacity={dim(s) ? 0.05 : 0.82} isAnimationActive={false} />
          ))}
        {(maMode === "30d" || maMode === "both") &&
          series.map((s, i) => (
            <Line key={`${s}_30d`} dataKey={`${s}_30d`} name={`${s} 30d`} stroke={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]} dot={false} activeDot={{ r: 4, stroke: CHART_COLORS.cursor, strokeWidth: 1 }} strokeDasharray="8 4" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" opacity={dim(s) ? 0.05 : 0.74} isAnimationActive={false} />
          ))}
      </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
