"use client";

import { useState } from "react";
import type { SentimentDaily, SentimentSummary, VolumeDaily } from "@/lib/types";

interface Props {
  volumeData?: VolumeDaily[];
  sentimentData?: SentimentSummary[];
  sentimentDaily?: SentimentDaily[];
}

interface HoverSignal {
  x: number;
  y: number;
  date: string;
  sentiment: number;
  volume: number;
}

const FALLBACK_SENTIMENT = [
  { date: "01", score: -0.22 },
  { date: "02", score: 0.02 },
  { date: "03", score: 0.1 },
  { date: "04", score: 0.48 },
  { date: "05", score: 0.28 },
  { date: "06", score: -0.18 },
  { date: "07", score: 0.16 },
];

const FALLBACK_VOLUME = [
  { date: "01", count: 32 },
  { date: "02", count: 68 },
  { date: "03", count: 84 },
  { date: "04", count: 127 },
  { date: "05", count: 103 },
  { date: "06", count: 74 },
  { date: "07", count: 162 },
];

function sentimentPercent(data: SentimentSummary[] | undefined, label: SentimentSummary["label"]) {
  const total = data?.reduce((sum, row) => sum + row.count, 0) ?? 0;
  const value = data?.find((row) => row.label === label)?.count ?? 0;
  return total ? Math.round((value / total) * 100) : 0;
}

function peakVolume(data: VolumeDaily[] | undefined) {
  if (!data?.length) return "0";
  return Math.max(...data.map((row) => row.count)).toLocaleString();
}

function aggregateSentiment(data: SentimentDaily[] | undefined) {
  if (!data?.length) return FALLBACK_SENTIMENT;
  const byDate = new Map<string, { total: number; count: number }>();
  for (const row of data) {
    const current = byDate.get(row.date) ?? { total: 0, count: 0 };
    current.total += row.mean_score;
    current.count += 1;
    byDate.set(row.date, current);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => (a > b ? 1 : -1))
    .slice(-36)
    .map(([date, value]) => ({ date, score: value.total / value.count }));
}

function aggregateVolume(data: VolumeDaily[] | undefined) {
  if (!data?.length) return FALLBACK_VOLUME;
  const byDate = new Map<string, number>();
  for (const row of data) {
    byDate.set(row.date, (byDate.get(row.date) ?? 0) + row.count);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => (a > b ? 1 : -1))
    .slice(-36)
    .map(([date, count]) => ({ date, count }));
}

function toPoints<T>(
  rows: T[],
  getValue: (row: T) => number,
  min: number,
  max: number,
  yTop = 36,
  yBottom = 214
) {
  const spread = Math.max(max - min, 0.0001);
  return rows.map((row, index) => {
    const x = rows.length === 1 ? 280 : 36 + (index / (rows.length - 1)) * 488;
    const normalized = (getValue(row) - min) / spread;
    const y = yBottom - normalized * (yBottom - yTop);
    return { x, y, value: getValue(row), row };
  });
}

function pathFromPoints(points: { x: number; y: number }[]) {
  if (!points.length) return "";
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
}

export function SignalStreamChart({ volumeData, sentimentData, sentimentDaily }: Props) {
  const [hoverSignal, setHoverSignal] = useState<HoverSignal | null>(null);
  const positive = sentimentPercent(sentimentData, "positive");
  const neutral = sentimentPercent(sentimentData, "neutral");
  const negative = sentimentPercent(sentimentData, "negative");
  const sentimentRows = aggregateSentiment(sentimentDaily);
  const volumeRows = aggregateVolume(volumeData);
  const sentimentPoints = toPoints(sentimentRows, (row) => row.score, -1, 1);
  const positivePoints = sentimentPoints.map((point) => ({ ...point, y: point.y - 18 - positive * 0.18 }));
  const neutralPoints = sentimentPoints.map((point, index) => ({ ...point, y: 125 + Math.sin(index * 0.9) * (16 + neutral * 0.08) }));
  const negativePoints = sentimentPoints.map((point) => ({ ...point, y: 250 - point.y + 34 - negative * 0.14 }));
  const maxVolume = Math.max(...volumeRows.map((row) => row.count), 1);
  const volumePoints = toPoints(volumeRows, (row) => row.count, 0, maxVolume, 58, 218);
  const volumeByDate = new Map(volumeRows.map((row) => [row.date, row.count]));
  const highVolumeMarkers = [...volumePoints]
    .sort((a, b) => b.value - a.value)
    .slice(0, 6)
    .sort((a, b) => a.x - b.x);
  const anomaly = negativePoints.reduce((lowest, point) => (point.y > lowest.y ? point : lowest), negativePoints[0]);
  const nearestSignal = (clientX: number, clientY: number, rect: DOMRect) => {
    const svgX = ((clientX - rect.left) / rect.width) * 560;
    const nearest = sentimentPoints.reduce((best, point) => {
      return Math.abs(point.x - svgX) < Math.abs(best.x - svgX) ? point : best;
    }, sentimentPoints[0]);
    const row = nearest?.row as { date: string; score: number } | undefined;
    if (!nearest || !row) return null;
    return {
      x: nearest.x,
      y: nearest.y,
      date: row.date,
      sentiment: row.score,
      volume: volumeByDate.get(row.date) ?? 0,
    };
  };

  return (
    <section className="command-panel relative min-h-[392px] overflow-hidden p-5">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_22%,rgba(49,211,143,0.11),transparent_28%),linear-gradient(135deg,rgba(190,112,58,0.08),transparent_38%)]" />
      <div className="relative flex items-start justify-between gap-4">
        <div>
          <p className="command-label">Sentiment Stream</p>
          <h2 className="mt-1 text-xl font-semibold tracking-normal text-foreground">Signal Command</h2>
          <p className="mt-1 max-w-lg text-xs leading-5 text-muted-foreground">
            Subreddit intelligence, live from the stream.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2 text-right font-mono text-[11px]">
          <div>
            <p className="text-signal-green">{positive}%</p>
            <p className="text-muted-foreground">pos</p>
          </div>
          <div>
            <p className="text-signal-yellow">{neutral}%</p>
            <p className="text-muted-foreground">neu</p>
          </div>
          <div>
            <p className="text-signal-red">{negative}%</p>
            <p className="text-muted-foreground">neg</p>
          </div>
        </div>
      </div>

      <div className="relative mt-5 h-[292px] rounded-lg border border-white/8 bg-black/18">
        <div className="absolute inset-0 signal-grid opacity-80" />
        <div className="absolute bottom-4 left-5 top-4 w-px bg-gradient-to-b from-transparent via-signal-copper to-transparent" />
        <div className="absolute left-2 top-4 flex h-[260px] flex-col justify-between font-mono text-[10px] text-muted-foreground">
          <span>+1.0</span>
          <span>0.0</span>
          <span>-1.0</span>
        </div>
        <svg
          className="absolute inset-x-8 bottom-6 top-3 h-[260px] w-[calc(100%-4rem)] overflow-visible"
          viewBox="0 0 560 250"
          role="img"
          aria-label="Layered sentiment signal stream"
          onMouseMove={(event) => setHoverSignal(nearestSignal(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect()))}
          onMouseLeave={() => setHoverSignal(null)}
        >
          <defs>
            <linearGradient id="streamGlow" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="#2fd58d" stopOpacity="0.18" />
              <stop offset="48%" stopColor="#c07a45" stopOpacity="0.26" />
              <stop offset="100%" stopColor="#ef5f54" stopOpacity="0.18" />
            </linearGradient>
            <filter id="softGlow">
              <feGaussianBlur stdDeviation="3" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <path d="M 22 44 H 542 M 22 96 H 542 M 22 148 H 542 M 22 200 H 542" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 8" />
          <path d={pathFromPoints(volumePoints)} fill="none" stroke="url(#streamGlow)" strokeWidth="42" strokeLinecap="round" strokeLinejoin="round" opacity="0.35" />
          <path d={pathFromPoints(positivePoints)} fill="none" stroke="#31d38f" strokeWidth="2.5" strokeLinejoin="round" filter="url(#softGlow)" />
          <path d={pathFromPoints(neutralPoints)} fill="none" stroke="#c07a45" strokeWidth="1.8" strokeDasharray="7 7" strokeLinejoin="round" opacity="0.9" />
          <path d={pathFromPoints(negativePoints)} fill="none" stroke="#ef5f54" strokeWidth="1.6" strokeLinejoin="round" opacity="0.78" />
          {highVolumeMarkers.map((point, index) => (
            <g key={`${point.x}-${point.value}`}>
              <line x1={point.x} x2={point.x} y1="34" y2="218" stroke={index % 2 ? "#c07a45" : "#31d38f"} strokeOpacity="0.32" strokeDasharray="2 10" />
              <circle cx={point.x} cy={point.y} r={index % 3 === 0 ? 4 : 3} fill={index % 2 ? "#c07a45" : "#31d38f"} opacity="0.9" />
            </g>
          ))}
          {anomaly && (
            <>
              <circle cx={anomaly.x} cy={anomaly.y} r="5" fill="#ef5f54" />
              <circle cx={anomaly.x} cy={anomaly.y} r="13" fill="none" stroke="#ef5f54" strokeOpacity="0.28" />
            </>
          )}
          {hoverSignal && (
            <g pointerEvents="none">
              <line x1={hoverSignal.x} x2={hoverSignal.x} y1="28" y2="222" stroke="#f6e7c8" strokeOpacity="0.55" strokeDasharray="3 5" />
              <circle cx={hoverSignal.x} cy={hoverSignal.y} r="6" fill="#081816" stroke="#f6e7c8" strokeWidth="1.5" />
              <circle cx={hoverSignal.x} cy={hoverSignal.y} r="2.5" fill="#31d38f" />
            </g>
          )}
        </svg>
        {hoverSignal && (
          <div
            className="pointer-events-none absolute z-20 min-w-36 rounded-lg border border-signal-copper/35 bg-[#081816]/95 px-3 py-2 text-[11px] text-foreground shadow-2xl"
            style={{
              left: `calc(2rem + ${(hoverSignal.x / 560) * (100 - 0)}%)`,
              top: `${Math.max(8, hoverSignal.y * 0.92)}px`,
              transform: hoverSignal.x > 420 ? "translateX(-105%)" : "translateX(10px)",
            }}
          >
            <p className="font-mono text-signal-copper">{hoverSignal.date}</p>
            <p className="mt-1 font-mono">sentiment {hoverSignal.sentiment.toFixed(3)}</p>
            <p className="font-mono text-muted-foreground">volume {hoverSignal.volume.toLocaleString()}</p>
          </div>
        )}
        <div className="absolute bottom-4 left-12 right-5 flex items-center justify-between font-mono text-[10px] text-muted-foreground">
          <span>{sentimentRows[0]?.date?.slice(5) ?? "start"}</span>
          <span>Peak volume {peakVolume(volumeData)}</span>
          <span>{sentimentRows.at(-1)?.date?.slice(5) ?? "now"}</span>
        </div>
      </div>
    </section>
  );
}
