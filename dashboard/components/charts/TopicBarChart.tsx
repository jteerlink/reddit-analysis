"use client";

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { TopicOverTime } from "@/lib/types";

interface Props {
  data: TopicOverTime[];
}

export function TopicBarChart({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <XAxis dataKey="week_start" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
        <YAxis tick={{ fontSize: 10 }} width={40} />
        <Tooltip contentStyle={{ background: "#141619", border: "1px solid #2d2f33", fontSize: 12 }} />
        <Bar dataKey="doc_count" fill="#F59E0B" name="Docs" isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
