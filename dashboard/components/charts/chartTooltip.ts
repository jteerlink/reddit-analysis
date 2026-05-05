export const CHART_COLORS = {
  green: "#31d38f",
  copper: "#c07a45",
  yellow: "#d7d856",
  red: "#ef5f54",
  violet: "#7c5cff",
  blue: "#60A5FA",
  foreground: "#e9f4ee",
  muted: "#8fa49f",
  grid: "rgba(255, 255, 255, 0.08)",
  cursor: "rgba(246, 231, 200, 0.55)",
};

export const CHART_SERIES_COLORS = [
  CHART_COLORS.green,
  CHART_COLORS.copper,
  CHART_COLORS.yellow,
  CHART_COLORS.red,
  CHART_COLORS.violet,
  CHART_COLORS.blue,
];

export const CHART_AXIS_PROPS = {
  axisLine: { stroke: "rgba(255, 255, 255, 0.12)" },
  tickLine: { stroke: "rgba(255, 255, 255, 0.12)" },
  tick: {
    fill: CHART_COLORS.muted,
    fontFamily: "var(--font-geist-mono)",
    fontSize: 10,
  },
};

export const CHART_GRID_PROPS = {
  stroke: CHART_COLORS.grid,
  strokeDasharray: "3 8",
  vertical: false,
};

export const CHART_LEGEND_PROPS = {
  wrapperStyle: {
    color: CHART_COLORS.muted,
    fontFamily: "var(--font-geist-mono)",
    fontSize: 11,
  },
};

export const CHART_TOOLTIP_PROPS = {
  contentStyle: {
    background: "rgba(8, 24, 22, 0.96)",
    border: "1px solid rgba(192, 122, 69, 0.35)",
    borderRadius: 8,
    boxShadow: "0 18px 48px rgba(0, 0, 0, 0.36)",
    color: "#e9f4ee",
    fontSize: 12,
  },
  labelStyle: {
    color: "#c07a45",
    fontFamily: "var(--font-geist-mono)",
    fontSize: 11,
  },
  itemStyle: {
    color: "#e9f4ee",
    fontFamily: "var(--font-geist-mono)",
    fontSize: 11,
  },
  cursor: {
    stroke: CHART_COLORS.cursor,
    strokeWidth: 1,
    strokeDasharray: "3 5",
  },
};
