import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}

export function ChartCard({ title, subtitle, children, action }: Props) {
  return (
    <Card className="command-panel overflow-hidden border-white/8 bg-card/82">
      <CardHeader className="flex-row items-start justify-between">
        <div>
          <CardTitle className="text-sm font-semibold text-foreground">{title}</CardTitle>
          {subtitle && <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{subtitle}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
