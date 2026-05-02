"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";
import type { Post } from "@/lib/types";

interface Props {
  data: Post[];
}

export function ConfidenceHistogram({ data }: Props) {
  const bins = Array.from({ length: 20 }, (_, i) => ({
    bin: (i / 20).toFixed(2),
    count: 0,
  }));
  for (const row of data) {
    const idx = Math.min(Math.floor(row.confidence * 20), 19);
    bins[idx].count++;
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={bins} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <XAxis dataKey="bin" tick={{ fontSize: 10 }} />
        <YAxis tick={{ fontSize: 10 }} width={40} />
        <Tooltip contentStyle={{ background: "#141619", border: "1px solid #2d2f33", fontSize: 12 }} />
        <ReferenceLine x="0.75" stroke="#F59E0B" strokeDasharray="4 2" label={{ value: "0.75", fill: "#F59E0B", fontSize: 10 }} />
        <Bar dataKey="count" fill="#60A5FA" name="Count" />
      </BarChart>
    </ResponsiveContainer>
  );
}
