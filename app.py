"""Reddit Analyzer — Streamlit dashboard entry point.

Run with:
    streamlit run app.py

Set REDDIT_DB_PATH env var to point at a non-default database path.
"""

import json
from datetime import datetime

import streamlit as st

from src.dashboard import charts, db

st.set_page_config(layout="wide", page_title="Reddit Analyzer")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Reddit Analyzer")

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

    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

    st.caption(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")

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

    # Metric row
    c1, c2, c3, c4 = st.columns(4)
    total_posts = int(summary["total_posts"].iloc[0]) if not summary.empty else 0
    total_comments = int(summary["total_comments"].iloc[0]) if not summary.empty else 0
    last_ts = summary["last_timestamp"].iloc[0] if not summary.empty else "—"
    c1.metric("Total Posts", f"{total_posts:,}")
    c2.metric("Total Comments", f"{total_comments:,}")
    c3.metric("Last Collection", str(last_ts)[:19] if last_ts else "—")
    c4.metric("Last ML Run", str(last_ml)[:19] if last_ml else "—")

    # Sentiment ratio
    if not sentiment.empty:
        st.subheader("Sentiment Breakdown")
        sc1, sc2, sc3 = st.columns(3)
        total_preds = sentiment["count"].sum()
        for col, label, color_label in [
            (sc1, "positive", "Positive"),
            (sc2, "neutral", "Neutral"),
            (sc3, "negative", "Negative"),
        ]:
            row = sentiment[sentiment["label"] == label]
            pct = (
                f"{row['count'].iloc[0] / total_preds * 100:.1f}%"
                if not row.empty and total_preds > 0
                else "—"
            )
            col.metric(color_label, pct)
    else:
        st.info("Run `python scripts/batch_inference.py` to populate sentiment data.")

    # Trending topics
    if not trending.empty:
        st.subheader("Top Trending Topics (this week)")
        display = trending.copy()
        display["keywords"] = display["keywords"].apply(lambda k: _keyword_preview(k))
        st.dataframe(
            display[["topic_id", "keywords", "doc_count"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Run `python scripts/train_topic_model.py` to populate topic data.")

    # Charts row
    vol_df = db.get_daily_volume(subreddits=_subs, days=30)
    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(charts.volume_bar(vol_df), use_container_width=True)
    with col_right:
        st.plotly_chart(charts.sentiment_donut(sentiment), use_container_width=True)


def render_sentiment() -> None:
    st.subheader("Sentiment Trends")

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
    sent_start = str(tab_dates[0]) if isinstance(tab_dates, (list, tuple)) and len(tab_dates) > 0 else _start
    sent_end = str(tab_dates[1]) if isinstance(tab_dates, (list, tuple)) and len(tab_dates) > 1 else _end

    daily_df = db.get_sentiment_daily(subreddits=_subs, days=90)

    if daily_df.empty:
        st.info("Run `python scripts/run_timeseries.py` to populate sentiment trends.")
        return

    # Filter to selected date range
    mask = (daily_df["date"] >= sent_start) & (daily_df["date"] <= sent_end)
    daily_df = daily_df[mask]

    cp_df = db.get_change_points(subreddits=_subs)
    fig = charts.sentiment_line(daily_df, ma_mode=ma_mode)
    fig = charts.change_point_shapes(fig, cp_df)
    st.plotly_chart(fig, use_container_width=True)

    fc_df = db.get_forecast(subreddits=_subs)
    if not fc_df.empty:
        st.subheader("Forecast")
        st.plotly_chart(
            charts.forecast_area(fc_df, actuals_df=daily_df),
            use_container_width=True,
        )
    else:
        st.info("No forecast data — run `python scripts/run_timeseries.py`.")


def render_topics() -> None:
    st.subheader("Topic Explorer")

    topics_df = db.get_topics()
    if topics_df.empty:
        st.info("Run `python scripts/train_topic_model.py` to populate topic data.")
        return

    # Build display table with keyword preview
    display_df = topics_df.copy()
    display_df["keywords_preview"] = display_df["keywords"].apply(
        lambda k: _keyword_preview(k)
    )

    # Emerging topics
    emerging_df = db.get_emerging_topics(days=7)
    if not emerging_df.empty:
        emerging_ids = set(emerging_df["topic_id"].tolist())
        display_df["emerging"] = display_df["topic_id"].isin(emerging_ids)
    else:
        emerging_ids = set()

    col_left, col_right = st.columns([3, 7])

    with col_left:
        st.markdown("**Topics**")
        topic_options = {
            f"{'[NEW] ' if row['topic_id'] in emerging_ids else ''}{row['keywords_preview']} ({row['doc_count']} docs)": row["topic_id"]
            for _, row in display_df.iterrows()
        }
        selected_label = st.selectbox(
            "Select topic",
            options=list(topic_options.keys()),
            label_visibility="collapsed",
        )
        selected_topic_id = topic_options[selected_label] if selected_label else None

    with col_right:
        if selected_topic_id is not None:
            topic_row = topics_df[topics_df["topic_id"] == selected_topic_id].iloc[0]
            st.markdown(f"**Keywords:** {_keyword_preview(topic_row['keywords'], n=10)}")

            tot_df = db.get_topic_over_time(selected_topic_id)
            st.plotly_chart(charts.topic_bar(tot_df), use_container_width=True)

            kw_str = _keywords_to_str(topic_row["keywords"])
            if kw_str:
                img_bytes = charts.wordcloud_image(kw_str)
                if img_bytes:
                    st.image(img_bytes, use_container_width=True)
                else:
                    st.caption(f"Keywords: {kw_str}")

    # Full-width heatmap
    st.subheader("Topic Sentiment Heatmap")
    heatmap_df = db.get_topic_heatmap(n=30)
    if not heatmap_df.empty:
        st.plotly_chart(charts.topic_heatmap(heatmap_df), use_container_width=True)
    else:
        st.info("Heatmap requires populated topic_over_time data.")


def render_deep_dive() -> None:
    st.subheader("Deep Dive")

    fc1, fc2, fc3, fc4 = st.columns([2, 2, 1, 1])
    with fc1:
        keyword = st.text_input("Keyword search", placeholder="Enter keyword...")
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
            "Content",
            options=["both", "post", "comment"],
            key="dd_ct",
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

    st.caption(f"{len(df):,} results")

    # Pagination
    page_size = 50
    total_pages = max(1, (len(df) - 1) // page_size + 1)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
    page_df = df.iloc[(page - 1) * page_size : page * page_size].copy()
    page_df["clean_text"] = page_df["clean_text"].str[:200]

    st.dataframe(
        page_df[["date", "subreddit", "content_type", "clean_text", "label", "confidence"]],
        use_container_width=True,
        hide_index=True,
    )

    # Export
    ex1, ex2 = st.columns(2)
    with ex1:
        st.download_button(
            "Download CSV",
            data=df.to_csv(index=False),
            file_name="reddit_results.csv",
            mime="text/csv",
        )
    with ex2:
        st.download_button(
            "Download JSON",
            data=df.to_json(orient="records", lines=True),
            file_name="reddit_results.jsonl",
            mime="application/json",
        )


def render_model_health() -> None:
    st.subheader("Model Health")

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

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    if not confidence_df.empty and "confidence" in confidence_df.columns:
        mean_conf = confidence_df["confidence"].mean()
        pct_high = (confidence_df["confidence"] >= 0.75).mean() * 100
        m1.metric("Mean Confidence", f"{mean_conf:.3f}")
        conf_color = "normal" if pct_high >= 75 else "inverse"
        m2.metric("Confidence ≥ 0.75", f"{pct_high:.1f}%", delta_color=conf_color)
    else:
        m1.metric("Mean Confidence", "—")
        m2.metric("Confidence ≥ 0.75", "—")

    vader_df = db.get_vader_agreement()
    if not vader_df.empty:
        overall_agreement = vader_df["agreement_rate"].mean()
        m3.metric("VADER Agreement", f"{overall_agreement:.1%}")
    else:
        m3.metric("VADER Agreement", "—")

    m4.metric("Last Retrain", last_retrain)

    # Charts
    col_left, col_right = st.columns(2)
    with col_left:
        if not confidence_df.empty:
            st.plotly_chart(
                charts.confidence_histogram(confidence_df), use_container_width=True
            )
        else:
            st.info("Run `python scripts/batch_inference.py` to populate predictions.")
    with col_right:
        if not vader_df.empty:
            st.plotly_chart(
                charts.vader_agreement_bar(vader_df), use_container_width=True
            )
        else:
            st.info("VADER agreement unavailable — run batch inference first.")

    st.info("No drift data yet — run `python scripts/detect_drift.py` (Week 6).")


# ---------------------------------------------------------------------------
# Tab routing
# ---------------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Overview", "Sentiment Trends", "Topic Explorer", "Deep Dive", "Model Health"]
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
