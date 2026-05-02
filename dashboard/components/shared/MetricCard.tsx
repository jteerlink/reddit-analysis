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
    <Card className="flex-1 min-w-0">
      <CardContent className="pt-4">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">{label}</p>
        <p className={cn("text-2xl font-semibold mt-1", accent && "text-amber-400")}>{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}
