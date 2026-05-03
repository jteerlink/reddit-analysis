"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from "recharts";
import type { VaderAgreement } from "@/lib/types";

interface Props {
  data: VaderAgreement[];
}

function rateColor(rate: number): string {
  if (rate >= 0.8) return "#34D399";
  if (rate >= 0.6) return "#F59E0B";
  return "#F87171";
}

export function VaderAgreementBar({ data }: Props) {
  const sorted = [...data].sort((a, b) => b.agreement_rate - a.agreement_rate);
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, sorted.length * 28)}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 4, right: 8, bottom: 0, left: 80 }}>
        <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 10 }} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
        <YAxis type="category" dataKey="subreddit" tick={{ fontSize: 10 }} width={80} />
        <Tooltip
          formatter={(v) => typeof v === "number" ? `${Math.round(v * 100)}%` : v}
          contentStyle={{ background: "#141619", border: "1px solid #2d2f33", fontSize: 12 }}
        />
        <Bar dataKey="agreement_rate" name="Agreement" isAnimationActive={false}>
          {sorted.map((entry) => (
            <Cell key={entry.subreddit} fill={rateColor(entry.agreement_rate)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
