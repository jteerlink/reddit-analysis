"use client";

import React, { Fragment, useState, useId } from "react";
import { AreaChart, Area, CartesianGrid, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { CHART_AXIS_PROPS, CHART_COLORS, CHART_GRID_PROPS, CHART_LEGEND_PROPS, CHART_SERIES_COLORS, CHART_TOOLTIP_PROPS } from "@/components/charts/chartTooltip";
import type { Forecast, SentimentDaily } from "@/lib/types";

interface Props {
  data: Forecast[];
  seriesLabels?: Record<string, string>;
  actualData?: SentimentDaily[];
}

interface ForecastBucket {
  yhatTotal: number;
  lowerTotal: number;
  upperTotal: number;
  count: number;
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
  minWidth: 200,
};

interface TEntry { name: string; value: unknown; color: string; }
type TPayload = readonly TEntry[];

function ForecastTooltip({ active, payload, label, showCI, showActuals }: {
  active?: boolean;
  payload?: TPayload;
  label?: string;
  showCI?: boolean;
  showActuals?: boolean;
}) {
  if (!active || !payload?.length) return null;

  type SeriesData = { color: string; forecast?: number; actual?: number; ci?: [number, number] };
  const groups = new Map<string, SeriesData>();

  for (const e of payload) {
    const name = e.name;
    if (name.endsWith(" signal band")) continue;

    if (name.endsWith(" forecast")) {
      const base = name.slice(0, -9);
      const g = groups.get(base) ?? { color: e.color };
      if (typeof e.value === "number") { g.forecast = e.value; g.color = e.color; }
      groups.set(base, g);
    } else if (name.endsWith(" actual")) {
      if (!showActuals) continue;
      const base = name.slice(0, -7);
      const g = groups.get(base) ?? { color: e.color };
      if (typeof e.value === "number") g.actual = e.value;
      groups.set(base, g);
    } else if (name.endsWith(" 95% CI")) {
      if (!showCI || e.value == null || !Array.isArray(e.value)) continue;
      const base = name.slice(0, -7);
      const g = groups.get(base) ?? { color: e.color };
      g.ci = e.value as [number, number];
      groups.set(base, g);
    }
  }

  interface FlatRow { key: string; label: string; value: string; color: string; muted?: boolean }
  const rows: FlatRow[] = [];
  for (const [name, g] of groups) {
    if (g.forecast != null) {
      rows.push({ key: `${name}-f`, label: `${name} forecast`, value: g.forecast.toFixed(3), color: g.color });
    }
    if (g.actual != null) {
      rows.push({ key: `${name}-a`, label: `${name} actual`, value: g.actual.toFixed(3), color: g.color, muted: true });
    }
    if (g.forecast != null && g.actual != null) {
      const delta = g.actual - g.forecast;
      rows.push({
        key: `${name}-d`,
        label: `${name} Δ`,
        value: `${delta >= 0 ? "+" : ""}${delta.toFixed(3)}`,
        color: delta >= 0 ? CHART_COLORS.green : CHART_COLORS.red,
      });
    }
    if (g.ci) {
      rows.push({ key: `${name}-ci`, label: `${name} 95% CI`, value: `${g.ci[0].toFixed(3)} ~ ${g.ci[1].toFixed(3)}`, color: g.color });
    }
  }

  return (
    <div style={TOOLTIP_STYLE}>
      <div style={{ color: "#c07a45", marginBottom: 10 }}>{label}</div>
      {rows.map((row) => (
        <div key={row.key} style={{ display: "flex", justifyContent: "space-between", gap: 24, marginTop: 4, opacity: row.muted ? 0.6 : 1 }}>
          <span style={{ color: row.color }}>{row.label}</span>
          <span style={{ color: "#e9f4ee" }}>{row.value}</span>
        </div>
      ))}
    </div>
  );
}

export function ForecastAreaChart({ data, seriesLabels = {}, actualData }: Props) {
  const chartId = useId().replace(/:/g, "");
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [showCI, setShowCI] = useState(true);
  const [showActuals, setShowActuals] = useState(true);
  const today = new Date().toISOString().slice(0, 10);

  const series = [...new Set(data.map((d) => seriesLabels[d.subreddit] ?? d.subreddit))];
  const seriesSet = new Set(series);

  const byDate: Record<string, Record<string, string | number | number[] | null>> = {};
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
    const sep = key.indexOf(":");
    const date = key.slice(0, sep);
    const label = key.slice(sep + 1);
    if (!byDate[date]) byDate[date] = { date };
    const ci: [number, number] = [bucket.lowerTotal / bucket.count, bucket.upperTotal / bucket.count];
    byDate[date][`${label}_yhat`] = bucket.yhatTotal / bucket.count;
    byDate[date][`${label}_ci`] = date > today ? ci : null;
    byDate[date][`${label}_ci_past`] = date <= today ? ci : null;
  }

  // Overlay actual sentiment for past dates
  if (actualData) {
    const actualBuckets = new Map<string, { total: number; count: number }>();
    for (const row of actualData) {
      if (!row.date || row.date > today || row.mean_score == null) continue;
      const label = seriesLabels[row.subreddit] ?? row.subreddit;
      if (!seriesSet.has(label)) continue;
      const key = `${row.date}\0${label}`;
      const b = actualBuckets.get(key) ?? { total: 0, count: 0 };
      b.total += row.mean_score;
      b.count += 1;
      actualBuckets.set(key, b);
    }
    for (const [key, b] of actualBuckets) {
      const sep = key.indexOf("\0");
      const date = key.slice(0, sep);
      const label = key.slice(sep + 1);
      if (!byDate[date]) byDate[date] = { date };
      byDate[date][`${label}_actual`] = b.total / b.count;
    }
  }

  const chartData = Object.values(byDate).sort((a, b) => (String(a.date) > String(b.date) ? 1 : -1));

  const dim = (s: string) => !!(highlighted && highlighted !== s);
  const hasActualData = !!actualData?.length;

  return (
    <div className="signal-chart-frame">
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 4, marginBottom: 8 }}>
        <button
          onClick={() => setShowActuals((v) => !v)}
          disabled={!hasActualData}
          className={`px-2 py-1 rounded text-xs transition-colors ${showActuals && hasActualData ? "bg-amber-500 text-black font-medium" : "text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:hover:text-muted-foreground"}`}
        >
          Actuals
        </button>
        <button
          onClick={() => setShowCI((v) => !v)}
          className={`px-2 py-1 rounded text-xs transition-colors ${showCI ? "bg-amber-500 text-black font-medium" : "text-muted-foreground hover:text-foreground"}`}
        >
          95% CI
        </button>
      </div>
      <ResponsiveContainer width="100%" height={400}>
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
        <Tooltip
          content={(props) => (
            <ForecastTooltip
              active={props.active}
              payload={props.payload as unknown as TPayload}
              label={String(props.label ?? "")}
              showCI={showCI}
              showActuals={showActuals && hasActualData}
            />
          )}
          cursor={CHART_TOOLTIP_PROPS.cursor}
        />
        <Legend
          {...CHART_LEGEND_PROPS}
          onClick={(entry) => {
            const name = entry.value ?? "";
            const base = name.replace(/ (95% CI|forecast|actual|signal band)$/, "");
            setHighlighted((prev) => prev === base ? null : base);
          }}
          wrapperStyle={{ ...CHART_LEGEND_PROPS.wrapperStyle, cursor: "pointer" }}
        />
        {/* Background glow streams */}
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
            opacity={dim(s) ? 0.03 : 0.2}
            legendType="none"
            activeDot={false}
            isAnimationActive={false}
          />
        ))}
        {series.map((s, i) => (
          <Fragment key={s}>
            {/* Past CI band — faint */}
            {showCI && (
              <Area
                dataKey={`${s}_ci_past`}
                name={`${s} 95% CI`}
                fill={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]}
                fillOpacity={0.05}
                stroke="none"
                legendType="none"
                opacity={dim(s) ? 0.1 : 1}
                isAnimationActive={false}
              />
            )}
            {/* Future CI band — full color */}
            {showCI && (
              <Area
                dataKey={`${s}_ci`}
                name={`${s} 95% CI`}
                fill={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]}
                fillOpacity={0.15}
                stroke="none"
                opacity={dim(s) ? 0.1 : 1}
                isAnimationActive={false}
              />
            )}
            {/* Actual observed values — muted, past only */}
            {showActuals && hasActualData && (
              <Area
                dataKey={`${s}_actual`}
                name={`${s} actual`}
                stroke={CHART_SERIES_COLORS[i % CHART_SERIES_COLORS.length]}
                strokeWidth={1.6}
                strokeOpacity={0.5}
                fill="none"
                dot={false}
                activeDot={{ r: 4, stroke: CHART_COLORS.cursor, strokeWidth: 1 }}
                legendType="none"
                connectNulls={false}
                opacity={dim(s) ? 0.1 : 1}
                isAnimationActive={false}
              />
            )}
            {/* Forecast line */}
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
              opacity={dim(s) ? 0.1 : 1}
              isAnimationActive={false}
            />
          </Fragment>
        ))}
      </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
