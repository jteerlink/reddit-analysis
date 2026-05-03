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
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
        <p className={cn("mt-1 font-mono text-2xl font-semibold", accent ? "text-signal-green" : "text-foreground")}>{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}
