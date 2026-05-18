import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  value?: string | number;
  sub?: string;
  accent?: boolean;
  state?: "ready" | "loading" | "empty" | "error";
  message?: string;
}

const STATE_LABEL = {
  ready: "No data",
  loading: "Loading",
  empty: "No data",
  error: "Unavailable",
};

export function MetricCard({ label, value, sub, accent, state = "ready", message }: Props) {
  const hasValue = state === "ready" && value !== undefined && value !== null && value !== "";

  return (
    <Card className="min-w-[150px] flex-1 border-border/80 bg-card/78">
      <CardContent className="pt-3">
        <p className="command-label">{label}</p>
        {hasValue ? (
          <p className={cn("mt-1.5 font-mono text-[28px] font-semibold leading-none tracking-[-0.01em] tabular-nums", accent ? "text-signal-green" : "text-foreground")}>{value}</p>
        ) : (
          <div
            aria-live="polite"
            role={state === "error" ? "alert" : "status"}
            className={cn(
              "mt-2 inline-flex min-h-7 items-center rounded-md border px-2.5 font-mono text-xs",
              state === "error"
                ? "border-signal-red/25 bg-signal-red/10 text-signal-red"
                : "border-border bg-muted/45 text-muted-foreground",
            )}
          >
            {STATE_LABEL[state] ?? "No data"}
          </div>
        )}
        {(message ?? sub) && <p className="mt-1 font-sans text-[11px] text-muted-foreground">{message ?? sub}</p>}
      </CardContent>
    </Card>
  );
}
