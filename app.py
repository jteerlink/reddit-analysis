"""Reddit Analyzer — Streamlit dashboard entry point.

Run with:
    streamlit run app.py

Set REDDIT_DB_PATH env var to point at a non-default database path.
"""

import json
from datetime import datetime

import streamlit as st

from src.dashboard import charts, db
from src.dashboard.pipeline import render_pipeline
from src.dashboard.theme import (
    chart_card,
    inject_theme,
    metric_card,
    section_header,
    sidebar_brand,
    sidebar_eyebrow,
    sidebar_footer,
    tab_group_header,
)

st.set_page_config(
    layout="wide",
    page_title="Reddit Analyzer",
    page_icon="📊",
    initial_sidebar_state="expanded",
)

inject_theme()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    sidebar_brand(
        title="Reddit Analyzer",
        subtitle="Sentiment & topic intelligence",
        eyebrow="Dashboard v1",
    )

    sidebar_eyebrow("Filters")

    known_subreddits = db.get_known_subreddits()
    selected_subreddits = st.multiselect(
        "Subreddits",
        options=known_subreddits,
        default=[],
        placeholder="All subreddits",
    )

    min_date, max_date = db.get_date_range()
    date_range = st.slider(
        "Date range",
        min_value=min_date,
        max_value=max_date,
        value=(min_date, max_date),
    )

    st.markdown("")  # spacer

    if st.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    sidebar_footer(f"Last refreshed · {datetime.now().strftime('%H:%M:%S')}")

# Convert selected_subreddits to tuple for cache-key hashing
_subs = tuple(selected_subreddits) if selected_subreddits else ()
_start = str(date_range[0])
_end = str(date_range[1])

# ---------------------------------------------------------------------------
# Helper: parse keyword JSON to plain string for word clouds
# ---------------------------------------------------------------------------


def _keywords_to_str(keywords_json: str) -> str:
    """Extract words from keywords JSON column into a space-separated string."""
    try:
        parsed = json.loads(keywords_json)
        words = []
        for item in parsed:
            if isinstance(item, str):
                words.append(item)
            elif isinstance(item, (list, tuple)) and item:
                words.append(str(item[0]))
        return " ".join(words)
    except Exception:
        return str(keywords_json)


def _keyword_preview(keywords_json: str, n: int = 5) -> str:
    """Return first N keywords as a comma-separated preview string."""
    text = _keywords_to_str(keywords_json)
    words = text.split()
    preview = ", ".join(words[:n])
    return f"{preview}..." if len(words) > n else preview


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------


def render_overview() -> None:
    summary = db.get_collection_summary()
    sentiment = db.get_sentiment_summary()
    trending = db.get_trending_topics(n=3)
    last_ml = db.get_last_ml_timestamp()

    section_header(
        "Overview",
        "Collection volume, sentiment mix, and the topics trending this week.",
        eyebrow="At a glance",
    )

    # Top metric row
    total_posts = int(summary["total_posts"].iloc[0]) if not summary.empty else 0
    total_comments = int(summary["total_comments"].iloc[0]) if not summary.empty else 0
    last_ts = summary["last_timestamp"].iloc[0] if not summary.empty else None
    last_ts_str = str(last_ts)[:19] if last_ts else "—"
    last_ml_str = str(last_ml)[:19] if last_ml else "—"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        metric_card("Total Posts", f"{total_posts:,}")
    with c2:
        metric_card("Total Comments", f"{total_comments:,}")
    with c3:
        metric_card("Last Collection", last_ts_str, compact=True)
    with c4:
        metric_card("Last ML Run", last_ml_str, compact=True)

    st.markdown("")  # spacer

    # Sentiment breakdown
    if not sentiment.empty:
        total_preds = sentiment["count"].sum()
        sc1, sc2, sc3 = st.columns(3)
        for col, label, human, dot in [
            (sc1, "positive", "Positive", "pos"),
            (sc2, "neutral", "Neutral", "neu"),
            (sc3, "negative", "Negative", "neg"),
        ]:
            row = sentiment[sentiment["label"] == label]
            if not row.empty and total_preds > 0:
                count = int(row["count"].iloc[0])
                pct = f"{count / total_preds * 100:.1f}%"
                delta = f"{count:,} predictions"
            else:
                pct = "—"
                delta = None
            with col:
                metric_card(human, pct, delta=delta, dot=dot)
    else:
        st.info("Run `python scripts/batch_inference.py` to populate sentiment data.")

    st.markdown("")  # spacer

    # Charts row
    vol_df = db.get_daily_volume(subreddits=_subs, days=30)
    col_left, col_right = st.columns([6, 4])
    with col_left:
        with chart_card("Daily volume", "Posts + comments per subreddit · last 30 days"):
            st.plotly_chart(charts.volume_bar(vol_df), use_container_width=True)
    with col_right:
        with chart_card("Sentiment mix", "All predictions to date"):
            st.plotly_chart(charts.sentiment_donut(sentiment), use_container_width=True)

    # Trending topics
    if not trending.empty:
        display = trending.copy()
        display["keywords"] = display["keywords"].apply(lambda k: _keyword_preview(k))
        with chart_card("Top trending topics", "Highest doc counts this week"):
            st.dataframe(
                display[["topic_id", "keywords", "doc_count"]],
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("Run `python scripts/train_topic_model.py` to populate topic data.")


def render_sentiment() -> None:
    section_header(
        "Sentiment trends",
        "Daily mean sentiment with optional rolling averages, change points, and a 14-day forecast.",
        eyebrow="Trends",
    )

    with st.container(border=True):
        ctrl1, ctrl2 = st.columns([2, 1])
        with ctrl1:
            tab_dates = st.date_input(
                "Date range",
                value=(date_range[0], date_range[1]),
                key="sent_dates",
            )
        with ctrl2:
            ma_mode = st.radio(
                "Moving average",
                options=["none", "7d", "30d", "both"],
                horizontal=True,
                key="ma_mode",
            )

    # Resolve date inputs safely
    sent_start = (
        str(tab_dates[0])
        if isinstance(tab_dates, (list, tuple)) and len(tab_dates) > 0
        else _start
    )
    sent_end = (
        str(tab_dates[1])
        if isinstance(tab_dates, (list, tuple)) and len(tab_dates) > 1
        else _end
    )

    daily_df = db.get_sentiment_daily(subreddits=_subs, days=90)

    if daily_df.empty:
        st.info("Run `python scripts/run_timeseries.py` to populate sentiment trends.")
        return

    mask = (daily_df["date"] >= sent_start) & (daily_df["date"] <= sent_end)
    daily_df = daily_df[mask]

    cp_df = db.get_change_points(subreddits=_subs)
    fig = charts.sentiment_line(daily_df, ma_mode=ma_mode)
    fig = charts.change_point_shapes(fig, cp_df)
    with chart_card(
        "Daily mean sentiment",
        "Dashed verticals mark detected change points",
    ):
        st.plotly_chart(fig, use_container_width=True)

    fc_df = db.get_forecast(subreddits=_subs)
    if not fc_df.empty:
        with chart_card(
            "14-day forecast",
            "Amber band is the 95% confidence interval · circles are actuals",
        ):
            st.plotly_chart(
                charts.forecast_area(fc_df, actuals_df=daily_df),
                use_container_width=True,
            )
    else:
        st.info("No forecast data — run `python scripts/run_timeseries.py`.")


def render_topics() -> None:
    section_header(
        "Topic explorer",
        "Browse discovered topics, inspect weekly volume, and scan sentiment across the full set.",
        eyebrow="Topics",
    )

    topics_df = db.get_topics()
    if topics_df.empty:
        st.info("Run `python scripts/train_topic_model.py` to populate topic data.")
        return

    display_df = topics_df.copy()
    display_df["keywords_preview"] = display_df["keywords"].apply(
        lambda k: _keyword_preview(k)
    )

    emerging_df = db.get_emerging_topics(days=7)
    if not emerging_df.empty:
        emerging_ids = set(emerging_df["topic_id"].tolist())
        display_df["emerging"] = display_df["topic_id"].isin(emerging_ids)
    else:
        emerging_ids = set()

    col_left, col_right = st.columns([3, 7])

    selected_topic_id = None
    with col_left:
        with chart_card("Topics", f"{len(display_df)} discovered · NEW = emerging this week"):
            topic_options = {
                f"{'[NEW] ' if row['topic_id'] in emerging_ids else ''}"
                f"{row['keywords_preview']} ({row['doc_count']} docs)": row["topic_id"]
                for _, row in display_df.iterrows()
            }
            selected_label = st.selectbox(
                "Select topic",
                options=list(topic_options.keys()),
                label_visibility="collapsed",
            )
            selected_topic_id = (
                topic_options[selected_label] if selected_label else None
            )

    with col_right:
        if selected_topic_id is not None:
            topic_row = topics_df[topics_df["topic_id"] == selected_topic_id].iloc[0]
            with chart_card(
                f"Topic #{selected_topic_id}",
                _keyword_preview(topic_row["keywords"], n=10),
            ):
                tot_df = db.get_topic_over_time(selected_topic_id)
                st.plotly_chart(charts.topic_bar(tot_df), use_container_width=True)

                kw_str = _keywords_to_str(topic_row["keywords"])
                if kw_str:
                    img_bytes = charts.wordcloud_image(kw_str)
                    if img_bytes:
                        st.image(img_bytes, use_container_width=True)
                    else:
                        st.caption(f"Keywords: {kw_str}")

    heatmap_df = db.get_topic_heatmap(n=30)
    if not heatmap_df.empty:
        with chart_card(
            "Sentiment heatmap",
            "Top 30 topics × weeks · coral = negative, emerald = positive",
        ):
            st.plotly_chart(charts.topic_heatmap(heatmap_df), use_container_width=True)
    else:
        st.info("Heatmap requires populated topic_over_time data.")


def render_deep_dive() -> None:
    section_header(
        "Deep dive",
        "Full-text search across posts and comments with sentiment and subreddit filters.",
        eyebrow="Search",
    )

    with st.container(border=True):
        fc1, fc2, fc3, fc4 = st.columns([3, 3, 2, 2])
        with fc1:
            keyword = st.text_input("Keyword", placeholder="Search posts and comments…")
        with fc2:
            sub_filter = st.multiselect(
                "Subreddits",
                options=known_subreddits,
                default=list(_subs) if _subs else [],
                key="dd_subs",
            )
        with fc3:
            label_filter = st.selectbox(
                "Sentiment",
                options=["all", "positive", "neutral", "negative"],
                key="dd_label",
            )
        with fc4:
            ct_filter = st.radio(
                "Type",
                options=["both", "post", "comment"],
                key="dd_ct",
                horizontal=True,
            )

    df = db.get_deep_dive(
        keyword=keyword,
        subreddits=tuple(sub_filter),
        start_date=_start,
        end_date=_end,
        label_filter=label_filter,
        content_type_filter=ct_filter,
    )

    if df.empty:
        st.info("No results match the current filters.")
        return

    # Pagination
    page_size = 50
    total_pages = max(1, (len(df) - 1) // page_size + 1)

    with chart_card("Results", f"{len(df):,} matches · {total_pages} pages"):
        page = st.number_input(
            "Page", min_value=1, max_value=total_pages, value=1, step=1
        )
        page_df = df.iloc[(page - 1) * page_size : page * page_size].copy()
        page_df["clean_text"] = page_df["clean_text"].str[:200]

        st.dataframe(
            page_df[
                ["date", "subreddit", "content_type", "clean_text", "label", "confidence"]
            ],
            use_container_width=True,
            hide_index=True,
        )

        ex1, ex2, _ = st.columns([1, 1, 3])
        with ex1:
            st.download_button(
                "Export CSV",
                data=df.to_csv(index=False),
                file_name="reddit_results.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with ex2:
            st.download_button(
                "Export JSON",
                data=df.to_json(orient="records", lines=True),
                file_name="reddit_results.jsonl",
                mime="application/json",
                use_container_width=True,
            )


def render_model_health() -> None:
    section_header(
        "Model health",
        "Prediction confidence, agreement with VADER, and retrain cadence.",
        eyebrow="Diagnostics",
    )

    confidence_df = db.get_deep_dive()  # full unfiltered set for confidence dist.

    # Last retrain from MLflow
    last_retrain = "Never"
    try:
        import mlflow

        runs = mlflow.search_runs(
            experiment_names=["reddit-analyzer-phase2"],
            order_by=["start_time DESC"],
            max_results=1,
        )
        if not runs.empty:
            last_retrain = str(runs["start_time"].iloc[0])[:19]
    except Exception:
        pass

    m1, m2, m3, m4 = st.columns(4)
    if not confidence_df.empty and "confidence" in confidence_df.columns:
        mean_conf = confidence_df["confidence"].mean()
        pct_high = (confidence_df["confidence"] >= 0.75).mean() * 100
        with m1:
            metric_card("Mean Confidence", f"{mean_conf:.3f}")
        with m2:
            metric_card(
                "Confidence ≥ 0.75",
                f"{pct_high:.1f}%",
                delta="threshold 75%",
                delta_good=pct_high >= 75,
            )
    else:
        with m1:
            metric_card("Mean Confidence", "—")
        with m2:
            metric_card("Confidence ≥ 0.75", "—")

    vader_df = db.get_vader_agreement()
    with m3:
        if not vader_df.empty:
            overall_agreement = vader_df["agreement_rate"].mean()
            metric_card(
                "VADER Agreement",
                f"{overall_agreement:.1%}",
                delta_good=overall_agreement >= 0.7,
            )
        else:
            metric_card("VADER Agreement", "—")

    with m4:
        metric_card("Last Retrain", last_retrain, compact=True)

    st.markdown("")  # spacer

    col_left, col_right = st.columns(2)
    with col_left:
        with chart_card("Prediction confidence", "Distribution across all predictions"):
            if not confidence_df.empty:
                st.plotly_chart(
                    charts.confidence_histogram(confidence_df),
                    use_container_width=True,
                )
            else:
                st.info(
                    "Run `python scripts/batch_inference.py` to populate predictions."
                )
    with col_right:
        with chart_card("VADER agreement", "Sign agreement between the model and VADER"):
            if not vader_df.empty:
                st.plotly_chart(
                    charts.vader_agreement_bar(vader_df),
                    use_container_width=True,
                )
            else:
                st.info("VADER agreement unavailable — run batch inference first.")

    st.info("No drift data yet — run `python scripts/detect_drift.py` (Week 6).")


# ---------------------------------------------------------------------------
# Tab routing
# ---------------------------------------------------------------------------

tab_group_header("Analytics", "Operations")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "Overview",
        "Sentiment Trends",
        "Topic Explorer",
        "Deep Dive",
        "Model Health",
        "Pipeline",
    ]
)

with tab1:
    render_overview()

with tab2:
    render_sentiment()

with tab3:
    render_topics()

with tab4:
    render_deep_dive()

with tab5:
    render_model_health()

with tab6:
    render_pipeline(db.DB_PATH)
