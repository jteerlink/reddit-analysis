"""Dashboard chart builders — pure functions that accept DataFrames and return figures.

All figures are re-themed via the shared Plotly template in `theme.py`. Chart titles are
stripped here because the surrounding `chart_card` owns titling at the DOM level.
"""

from io import BytesIO
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.dashboard.theme import (
    ACCENT,
    BORDER,
    COMPACT_MARGIN,
    DIVERGING_SCALE,
    ELEVATED,
    PLOTLY_TEMPLATE,
    SENTIMENT_COLORS,
    SURFACE,
    TEXT_MUTED,
    TEXT_SUBTLE,
)


def _apply_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(template=PLOTLY_TEMPLATE, title=None, margin=COMPACT_MARGIN)
    return fig


# ---------------------------------------------------------------------------
# Overview / sentiment charts
# ---------------------------------------------------------------------------


def volume_bar(df: pd.DataFrame) -> go.Figure:
    """Stacked bar: daily post+comment volume per subreddit."""
    if df.empty:
        return _empty_fig("No volume data yet")
    fig = px.bar(
        df,
        x="date",
        y="count",
        color="subreddit",
        barmode="stack",
        labels={"count": "Posts + Comments", "date": ""},
    )
    fig.update_traces(marker_line_width=0)
    fig.update_layout(bargap=0.18, legend=dict(orientation="h", y=-0.2))
    return _apply_theme(fig)


def sentiment_donut(df: pd.DataFrame) -> go.Figure:
    """Donut chart of sentiment label distribution."""
    if df.empty:
        return _empty_fig("No sentiment data yet")
    order = ["positive", "neutral", "negative"]
    df = df.set_index("label").reindex(order).dropna().reset_index()
    colors = [SENTIMENT_COLORS.get(lbl, "#BDC3C7") for lbl in df["label"]]
    fig = go.Figure(
        go.Pie(
            labels=df["label"],
            values=df["count"],
            hole=0.62,
            pull=[0.01] * len(df),
            marker=dict(colors=colors, line=dict(color=SURFACE, width=2)),
            textinfo="percent",
            textfont=dict(family="Geist Mono, monospace", size=13),
            hovertemplate="<b>%{label}</b><br>%{value:,} predictions<br>%{percent}<extra></extra>",
        )
    )
    fig.update_layout(
        legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"),
        margin=COMPACT_MARGIN,
    )
    return _apply_theme(fig)


def sentiment_line(df: pd.DataFrame, ma_mode: str = "none") -> go.Figure:
    """Line chart of daily mean sentiment per subreddit with optional moving averages."""
    if df.empty:
        return _empty_fig("No sentiment trend data yet")

    fig = go.Figure()
    for sub in df["subreddit"].unique():
        sub_df = df[df["subreddit"] == sub].sort_values("date")
        fig.add_trace(
            go.Scatter(
                x=sub_df["date"],
                y=sub_df["mean_score"],
                name=str(sub),
                mode="lines",
                line=dict(width=2.5, shape="spline", smoothing=0.6),
            )
        )
        if ma_mode in ("7d", "both") and "rolling_7d" in sub_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=sub_df["date"],
                    y=sub_df["rolling_7d"],
                    name=f"{sub} · 7d",
                    mode="lines",
                    line=dict(width=1.2, dash="dot"),
                    opacity=0.55,
                )
            )
        if ma_mode in ("30d", "both") and "rolling_30d" in sub_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=sub_df["date"],
                    y=sub_df["rolling_30d"],
                    name=f"{sub} · 30d",
                    mode="lines",
                    line=dict(width=1.2, dash="dash"),
                    opacity=0.5,
                )
            )

    fig.update_layout(
        xaxis_title="",
        yaxis_title="Sentiment score",
        legend=dict(
            orientation="h",
            y=1.08,
            x=0,
            xanchor="left",
            yanchor="bottom",
        ),
        hovermode="x unified",
    )
    return _apply_theme(fig)


def change_point_shapes(fig: go.Figure, df: pd.DataFrame) -> go.Figure:
    """Add vertical dashed lines + top-annotation dots for change points."""
    if df.empty:
        return fig
    for _, row in df.iterrows():
        mag = row.get("magnitude") or 0
        color = SENTIMENT_COLORS["positive"] if mag >= 0 else SENTIMENT_COLORS["negative"]
        fig.add_vline(
            x=row["date"],
            line=dict(color=color, width=1, dash="dash"),
            opacity=0.5,
        )
    return fig


def forecast_area(
    forecast_df: pd.DataFrame, actuals_df: Optional[pd.DataFrame] = None
) -> go.Figure:
    """Line + amber confidence band for Prophet forecast with faint actuals overlay."""
    if forecast_df.empty:
        return _empty_fig("No forecast data yet")

    fig = go.Figure()
    for sub in forecast_df["subreddit"].unique():
        sub_fc = forecast_df[forecast_df["subreddit"] == sub].sort_values("date")

        fig.add_trace(
            go.Scatter(
                x=pd.concat([sub_fc["date"], sub_fc["date"].iloc[::-1]]),
                y=pd.concat([sub_fc["yhat_upper"], sub_fc["yhat_lower"].iloc[::-1]]),
                fill="toself",
                fillcolor="rgba(245,158,11,0.18)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                hoverinfo="skip",
                name=f"{sub} 95% CI",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sub_fc["date"],
                y=sub_fc["yhat"],
                name=f"{sub} forecast",
                mode="lines",
                line=dict(width=2.2, color=ACCENT, shape="spline", smoothing=0.6),
            )
        )

    if actuals_df is not None and not actuals_df.empty:
        for sub in actuals_df["subreddit"].unique():
            sub_act = actuals_df[actuals_df["subreddit"] == sub].sort_values("date")
            fig.add_trace(
                go.Scatter(
                    x=sub_act["date"],
                    y=sub_act["mean_score"],
                    name=f"{sub} actual",
                    mode="markers",
                    marker=dict(
                        size=5,
                        symbol="circle-open",
                        color=TEXT_MUTED,
                        line=dict(width=1.25),
                    ),
                    opacity=0.7,
                )
            )

    fig.update_layout(
        xaxis_title="",
        yaxis_title="Sentiment score",
        legend=dict(orientation="h", y=1.08, x=0, xanchor="left", yanchor="bottom"),
        hovermode="x unified",
    )
    return _apply_theme(fig)


# ---------------------------------------------------------------------------
# Topic charts
# ---------------------------------------------------------------------------


def topic_bar(df: pd.DataFrame) -> go.Figure:
    """Single-series weekly doc count bar for one topic."""
    if df.empty:
        return _empty_fig("No topic time-series data yet")
    fig = px.bar(
        df,
        x="week_start",
        y="doc_count",
        labels={"week_start": "", "doc_count": "Documents"},
    )
    fig.update_traces(
        marker_color=ACCENT,
        marker_line_color=ELEVATED,
        marker_line_width=1,
    )
    fig.update_layout(bargap=0.22)
    return _apply_theme(fig)


def topic_heatmap(pivot_df: pd.DataFrame) -> go.Figure:
    """Heatmap: topics (rows) × weeks (cols), colored by avg_sentiment."""
    if pivot_df.empty:
        return _empty_fig("No heatmap data yet")
    fig = px.imshow(
        pivot_df,
        color_continuous_scale=DIVERGING_SCALE,
        color_continuous_midpoint=0,
        labels=dict(x="Week", y="Topic ID", color="Sentiment"),
        aspect="auto",
    )
    fig.update_coloraxes(
        colorbar=dict(
            thickness=10,
            len=0.65,
            outlinewidth=0,
            tickfont=dict(color=TEXT_MUTED, size=10),
            title=dict(text=""),
        )
    )
    return _apply_theme(fig)


# ---------------------------------------------------------------------------
# Model health charts
# ---------------------------------------------------------------------------


def confidence_histogram(df: pd.DataFrame) -> go.Figure:
    """Amber histogram of prediction confidence with a slate 0.75 threshold line."""
    if df.empty or "confidence" not in df.columns:
        return _empty_fig("No confidence data yet")
    fig = px.histogram(
        df,
        x="confidence",
        nbins=24,
        labels={"confidence": "Confidence", "count": ""},
    )
    fig.update_traces(
        marker_color=ACCENT,
        marker_line_color=ELEVATED,
        marker_line_width=1,
        opacity=0.9,
    )
    fig.add_vline(
        x=0.75,
        line=dict(color=TEXT_MUTED, width=1.5, dash="dash"),
        annotation_text="0.75 threshold",
        annotation_position="top right",
        annotation_font=dict(color=TEXT_MUTED, size=11, family="Geist Mono, monospace"),
    )
    fig.update_layout(bargap=0.04)
    return _apply_theme(fig)


def vader_agreement_bar(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of VADER / model agreement per subreddit."""
    if df.empty:
        return _empty_fig("No VADER agreement data yet")
    df_sorted = df.sort_values("agreement_rate")
    fig = px.bar(
        df_sorted,
        x="agreement_rate",
        y="subreddit",
        orientation="h",
        labels={"agreement_rate": "Agreement rate", "subreddit": ""},
        range_x=[0, 1],
        color="agreement_rate",
        color_continuous_scale=[
            [0.0, SENTIMENT_COLORS["negative"]],
            [0.5, TEXT_MUTED],
            [1.0, SENTIMENT_COLORS["positive"]],
        ],
    )
    fig.update_traces(marker_line_width=0)
    fig.update_coloraxes(showscale=False)
    fig.add_vline(x=0.5, line=dict(color=BORDER, width=1, dash="dash"), opacity=0.6)
    fig.update_layout(bargap=0.35)
    return _apply_theme(fig)


# ---------------------------------------------------------------------------
# Wordcloud
# ---------------------------------------------------------------------------


def wordcloud_image(keywords_str: str) -> Optional[bytes]:
    """Generate a word cloud from space-separated keywords. Returns PNG bytes."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from wordcloud import WordCloud

        wc = WordCloud(
            width=800,
            height=360,
            background_color=SURFACE,
            colormap="YlOrBr_r",
            prefer_horizontal=0.92,
            collocations=False,
            margin=6,
        ).generate(keywords_str)
        fig, ax = plt.subplots(figsize=(6.5, 2.9), facecolor=SURFACE)
        ax.set_facecolor(SURFACE)
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        buf = BytesIO()
        fig.savefig(
            buf,
            format="png",
            bbox_inches="tight",
            dpi=150,
            facecolor=SURFACE,
            pad_inches=0,
        )
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except ImportError:
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_fig(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        annotations=[
            dict(
                text=message,
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(color=TEXT_SUBTLE, family="Geist, sans-serif", size=13),
            )
        ],
        shapes=[
            dict(
                type="rect",
                xref="paper",
                yref="paper",
                x0=0.02,
                x1=0.98,
                y0=0.12,
                y1=0.88,
                line=dict(color=BORDER, width=1, dash="dot"),
                fillcolor="rgba(0,0,0,0)",
            )
        ],
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        height=260,
    )
    return _apply_theme(fig)
