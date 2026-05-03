"use client";

import type { SentimentSummary, VolumeDaily } from "@/lib/types";

interface Props {
  volumeData?: VolumeDaily[];
  sentimentData?: SentimentSummary[];
}

const POSITIVE_PATH = "M 30 178 C 88 112, 142 142, 196 91 S 305 64, 362 116 S 462 204, 540 118";
const NEUTRAL_PATH = "M 28 144 C 88 151, 142 117, 205 139 S 319 166, 378 132 S 468 91, 540 146";
const NEGATIVE_PATH = "M 28 92 C 91 126, 129 206, 196 173 S 300 105, 354 158 S 451 223, 540 188";

function sentimentPercent(data: SentimentSummary[] | undefined, label: SentimentSummary["label"]) {
  const total = data?.reduce((sum, row) => sum + row.count, 0) ?? 0;
  const value = data?.find((row) => row.label === label)?.count ?? 0;
  return total ? Math.round((value / total) * 100) : 0;
}

function peakVolume(data: VolumeDaily[] | undefined) {
  if (!data?.length) return "0";
  return Math.max(...data.map((row) => row.count)).toLocaleString();
}

export function SignalStreamChart({ volumeData, sentimentData }: Props) {
  const positive = sentimentPercent(sentimentData, "positive");
  const neutral = sentimentPercent(sentimentData, "neutral");
  const negative = sentimentPercent(sentimentData, "negative");

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
        <svg className="absolute inset-x-8 bottom-6 top-3 h-[260px] w-[calc(100%-4rem)] overflow-visible" viewBox="0 0 560 250" role="img" aria-label="Layered sentiment signal stream">
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
          <path d="M 40 210 C 104 170, 147 183, 194 145 C 260 92, 309 111, 352 83 C 421 38, 479 84, 536 51" fill="none" stroke="url(#streamGlow)" strokeWidth="42" strokeLinecap="round" opacity="0.35" />
          <path d={POSITIVE_PATH} fill="none" stroke="#31d38f" strokeWidth="2.5" filter="url(#softGlow)" />
          <path d={NEUTRAL_PATH} fill="none" stroke="#c07a45" strokeWidth="1.8" strokeDasharray="7 7" opacity="0.9" />
          <path d={NEGATIVE_PATH} fill="none" stroke="#ef5f54" strokeWidth="1.6" opacity="0.78" />
          {[72, 138, 226, 316, 414, 500].map((x, index) => (
            <g key={x}>
              <line x1={x} x2={x} y1="34" y2="218" stroke={index % 2 ? "#c07a45" : "#31d38f"} strokeOpacity="0.32" strokeDasharray="2 10" />
              <circle cx={x} cy={index % 2 ? 112 : 164} r={index % 3 === 0 ? 4 : 3} fill={index % 2 ? "#c07a45" : "#31d38f"} opacity="0.9" />
            </g>
          ))}
          <circle cx="452" cy="205" r="5" fill="#ef5f54" />
          <circle cx="452" cy="205" r="13" fill="none" stroke="#ef5f54" strokeOpacity="0.28" />
        </svg>
        <div className="absolute bottom-4 left-12 right-5 flex items-center justify-between font-mono text-[10px] text-muted-foreground">
          <span>30d</span>
          <span>Peak volume {peakVolume(volumeData)}</span>
          <span>Now</span>
        </div>
      </div>
    </section>
  );
}
