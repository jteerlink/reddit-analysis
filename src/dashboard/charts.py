"""Dashboard chart builders — pure functions that accept DataFrames and return figures."""

from io import BytesIO
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

_COMPACT = dict(l=20, r=20, t=40, b=20)
_SENTIMENT_COLORS = {"positive": "#2ecc71", "neutral": "#95a5a6", "negative": "#e74c3c"}


def volume_bar(df: pd.DataFrame) -> go.Figure:
    """Stacked bar: daily post+comment volume per subreddit."""
    if df.empty:
        return _empty_fig("No volume data")
    fig = px.bar(
        df,
        x="date",
        y="count",
        color="subreddit",
        barmode="stack",
        title="Daily Volume by Subreddit",
        labels={"count": "Posts + Comments", "date": "Date"},
    )
    fig.update_layout(margin=_COMPACT)
    return fig


def sentiment_donut(df: pd.DataFrame) -> go.Figure:
    """Donut chart of sentiment label distribution."""
    if df.empty:
        return _empty_fig("No sentiment data")
    color_map = [_SENTIMENT_COLORS.get(lbl, "#bdc3c7") for lbl in df["label"]]
    fig = go.Figure(
        go.Pie(
            labels=df["label"],
            values=df["count"],
            hole=0.5,
            marker=dict(colors=color_map),
        )
    )
    fig.update_layout(title="Sentiment Distribution", margin=_COMPACT)
    return fig


def sentiment_line(df: pd.DataFrame, ma_mode: str = "none") -> go.Figure:
    """Line chart of daily mean sentiment per subreddit with optional moving averages."""
    if df.empty:
        return _empty_fig("No sentiment trend data")

    fig = go.Figure()
    for sub in df["subreddit"].unique():
        sub_df = df[df["subreddit"] == sub].sort_values("date")
        fig.add_trace(
            go.Scatter(
                x=sub_df["date"],
                y=sub_df["mean_score"],
                name=sub,
                mode="lines",
                line=dict(width=2),
            )
        )
        if ma_mode in ("7d", "both") and "rolling_7d" in sub_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=sub_df["date"],
                    y=sub_df["rolling_7d"],
                    name=f"{sub} 7d avg",
                    mode="lines",
                    line=dict(width=1, dash="dot"),
                    showlegend=True,
                )
            )
        if ma_mode in ("30d", "both") and "rolling_30d" in sub_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=sub_df["date"],
                    y=sub_df["rolling_30d"],
                    name=f"{sub} 30d avg",
                    mode="lines",
                    line=dict(width=1, dash="dash"),
                    showlegend=True,
                )
            )

    fig.update_layout(
        title="Daily Mean Sentiment",
        xaxis_title="Date",
        yaxis_title="Sentiment Score",
        margin=_COMPACT,
    )
    return fig


def change_point_shapes(fig: go.Figure, df: pd.DataFrame) -> go.Figure:
    """Add vertical dashed lines for change points to an existing figure."""
    if df.empty:
        return fig
    for _, row in df.iterrows():
        color = "#2ecc71" if (row["magnitude"] or 0) >= 0 else "#e74c3c"
        fig.add_vline(
            x=row["date"],
            line=dict(color=color, width=1, dash="dash"),
            opacity=0.6,
        )
    return fig


def forecast_area(
    forecast_df: pd.DataFrame, actuals_df: Optional[pd.DataFrame] = None
) -> go.Figure:
    """Line chart with shaded confidence band for Prophet forecast."""
    if forecast_df.empty:
        return _empty_fig("No forecast data")

    fig = go.Figure()
    for sub in forecast_df["subreddit"].unique():
        sub_fc = forecast_df[forecast_df["subreddit"] == sub].sort_values("date")

        fig.add_trace(
            go.Scatter(
                x=pd.concat([sub_fc["date"], sub_fc["date"].iloc[::-1]]),
                y=pd.concat([sub_fc["yhat_upper"], sub_fc["yhat_lower"].iloc[::-1]]),
                fill="toself",
                fillcolor="rgba(100,149,237,0.2)",
                line=dict(color="rgba(255,255,255,0)"),
                showlegend=False,
                name=f"{sub} 95% CI",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sub_fc["date"],
                y=sub_fc["yhat"],
                name=f"{sub} forecast",
                mode="lines",
                line=dict(width=2, color="cornflowerblue"),
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
                    marker=dict(size=4, opacity=0.6),
                )
            )

    fig.update_layout(
        title="Sentiment Forecast (14-day)",
        xaxis_title="Date",
        yaxis_title="Sentiment Score",
        margin=_COMPACT,
    )
    return fig


def topic_bar(df: pd.DataFrame) -> go.Figure:
    """Bar chart of weekly doc count for a single topic."""
    if df.empty:
        return _empty_fig("No topic time-series data")
    fig = px.bar(
        df,
        x="week_start",
        y="doc_count",
        title="Topic Volume Over Time",
        labels={"week_start": "Week", "doc_count": "Documents"},
    )
    fig.update_layout(margin=_COMPACT)
    return fig


def topic_heatmap(pivot_df: pd.DataFrame) -> go.Figure:
    """Heatmap: topics (rows) × weeks (cols), colored by avg_sentiment."""
    if pivot_df.empty:
        return _empty_fig("No heatmap data")
    fig = px.imshow(
        pivot_df,
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=0,
        title="Topic Sentiment Heatmap (top 30 topics)",
        labels=dict(x="Week", y="Topic ID", color="Avg Sentiment"),
        aspect="auto",
    )
    fig.update_layout(margin=_COMPACT)
    return fig


def confidence_histogram(df: pd.DataFrame) -> go.Figure:
    """Histogram of prediction confidence with 0.75 threshold line."""
    if df.empty or "confidence" not in df.columns:
        return _empty_fig("No confidence data")
    fig = px.histogram(
        df,
        x="confidence",
        nbins=20,
        title="Prediction Confidence Distribution",
        labels={"confidence": "Confidence", "count": "Count"},
    )
    fig.add_vline(
        x=0.75,
        line=dict(color="red", width=2, dash="dash"),
        annotation_text="0.75 threshold",
        annotation_position="top right",
    )
    fig.update_layout(margin=_COMPACT)
    return fig


def vader_agreement_bar(df: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of VADER vs model agreement rate per subreddit."""
    if df.empty:
        return _empty_fig("No VADER agreement data")
    df_sorted = df.sort_values("agreement_rate")
    fig = px.bar(
        df_sorted,
        x="agreement_rate",
        y="subreddit",
        orientation="h",
        title="VADER / Model Agreement Rate by Subreddit",
        labels={"agreement_rate": "Agreement Rate", "subreddit": "Subreddit"},
        range_x=[0, 1],
    )
    fig.add_vline(x=0.5, line=dict(color="gray", dash="dash"), opacity=0.4)
    fig.update_layout(margin=_COMPACT)
    return fig


def wordcloud_image(keywords_str: str) -> Optional[bytes]:
    """Generate a word cloud from space-separated keywords. Returns PNG bytes."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from wordcloud import WordCloud

        wc = WordCloud(
            width=600, height=280, background_color="white", collocations=False
        ).generate(keywords_str)
        fig, ax = plt.subplots(figsize=(6, 2.8))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
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
            dict(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
        ],
        margin=_COMPACT,
    )
    return fig
