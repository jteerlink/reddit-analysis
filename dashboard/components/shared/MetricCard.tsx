import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  value: string | number;
  sub?: string;
  accent?: boolean;
}

export function MetricCard({ label, value, sub, accent }: Props) {
  return (
    <Card className="min-w-[150px] flex-1 border-border/80 bg-card/78">
      <CardContent className="pt-3">
        <p className="command-label">{label}</p>
        <p className={cn("mt-1.5 font-mono text-[28px] font-semibold leading-none tracking-[-0.01em] tabular-nums", accent ? "text-signal-green" : "text-foreground")}>{value}</p>
        {sub && <p className="mt-1 font-sans text-[11px] text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
}
