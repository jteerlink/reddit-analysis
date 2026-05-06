CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT,
    upvotes INTEGER,
    timestamp TIMESTAMPTZ,
    subreddit TEXT,
    author TEXT,
    author_karma INTEGER,
    url TEXT,
    num_comments INTEGER,
    content_type TEXT DEFAULT 'post' CHECK (content_type IN ('post', 'comment')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    content TEXT NOT NULL,
    upvotes INTEGER,
    timestamp TIMESTAMPTZ,
    subreddit TEXT,
    author TEXT,
    author_karma INTEGER,
    post_id TEXT REFERENCES posts(id),
    content_type TEXT DEFAULT 'comment',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_metrics (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    requests_made INTEGER,
    requests_failed INTEGER,
    rate_limit_hits INTEGER,
    circuit_breaker_trips INTEGER
);

CREATE TABLE IF NOT EXISTS collection_metadata (
    id BIGSERIAL PRIMARY KEY,
    subreddit TEXT NOT NULL,
    collection_timestamp TIMESTAMPTZ NOT NULL,
    posts_collected INTEGER DEFAULT 0,
    comments_collected INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(subreddit, collection_timestamp)
);

CREATE TABLE IF NOT EXISTS batch_collections (
    id BIGSERIAL PRIMARY KEY,
    subreddit TEXT NOT NULL,
    collection_timestamp TIMESTAMPTZ NOT NULL,
    posts_collected INTEGER DEFAULT 0,
    comments_collected INTEGER DEFAULT 0,
    processing_time_seconds DOUBLE PRECISION DEFAULT 0,
    batch_status TEXT DEFAULT 'completed',
    storage_timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(subreddit, collection_timestamp)
);

CREATE TABLE IF NOT EXISTS preprocessed (
    id TEXT PRIMARY KEY,
    content_type TEXT NOT NULL,
    raw_text TEXT,
    clean_text TEXT,
    token_count INTEGER,
    is_filtered BOOLEAN NOT NULL DEFAULT FALSE,
    filter_reason TEXT,
    embedding_key TEXT,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sentiment_predictions (
    id TEXT PRIMARY KEY,
    content_type TEXT,
    label TEXT,
    confidence DOUBLE PRECISION,
    logits JSONB,
    model_version TEXT,
    predicted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS topics (
    topic_id INTEGER PRIMARY KEY,
    keywords TEXT NOT NULL,
    doc_count INTEGER NOT NULL DEFAULT 0,
    coherence_score DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS topic_assignments (
    id TEXT PRIMARY KEY REFERENCES preprocessed(id),
    topic_id INTEGER NOT NULL,
    probability DOUBLE PRECISION,
    assigned_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS topic_over_time (
    topic_id INTEGER NOT NULL,
    week_start DATE NOT NULL,
    doc_count INTEGER NOT NULL DEFAULT 0,
    avg_sentiment DOUBLE PRECISION,
    PRIMARY KEY (topic_id, week_start)
);

CREATE TABLE IF NOT EXISTS sentiment_daily (
    subreddit TEXT NOT NULL,
    date DATE NOT NULL,
    mean_score DOUBLE PRECISION,
    pos_count INTEGER NOT NULL DEFAULT 0,
    neu_count INTEGER NOT NULL DEFAULT 0,
    neg_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (subreddit, date)
);

CREATE TABLE IF NOT EXISTS sentiment_moving_avg (
    subreddit TEXT NOT NULL,
    date DATE NOT NULL,
    rolling_7d DOUBLE PRECISION,
    rolling_30d DOUBLE PRECISION,
    PRIMARY KEY (subreddit, date)
);

CREATE TABLE IF NOT EXISTS change_points (
    subreddit TEXT NOT NULL,
    date DATE NOT NULL,
    magnitude DOUBLE PRECISION,
    PRIMARY KEY (subreddit, date)
);

CREATE TABLE IF NOT EXISTS sentiment_forecast (
    subreddit TEXT NOT NULL,
    date DATE NOT NULL,
    yhat DOUBLE PRECISION,
    yhat_lower DOUBLE PRECISION,
    yhat_upper DOUBLE PRECISION,
    PRIMARY KEY (subreddit, date)
);

CREATE TABLE IF NOT EXISTS topic_sentiment_trends (
    topic_id INTEGER NOT NULL,
    date DATE NOT NULL,
    mean_sentiment DOUBLE PRECISION,
    rolling_7d DOUBLE PRECISION,
    PRIMARY KEY (topic_id, date)
);

CREATE TABLE IF NOT EXISTS analysis_schema_version (
    key TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS llm_model_registry (
    model_name TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'ollama',
    available BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB,
    discovered_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    provider TEXT,
    model_name TEXT,
    prompt_version TEXT,
    input_hash TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_category TEXT,
    error_message TEXT,
    resume_token TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analysis_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    idempotency_key TEXT NOT NULL UNIQUE,
    payload JSONB,
    payload_location TEXT,
    checksum TEXT,
    content_type TEXT NOT NULL DEFAULT 'application/json',
    schema_version INTEGER NOT NULL DEFAULT 1,
    provider TEXT,
    model_name TEXT,
    prompt_version TEXT,
    source_input_hash TEXT NOT NULL,
    freshness_timestamp TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    lease_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    error_category TEXT,
    error_message TEXT,
    retry_after TIMESTAMPTZ,
    resume_token TEXT,
    parent_artifact_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS artifact_status_history (
    id BIGSERIAL PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    from_status TEXT,
    to_status TEXT NOT NULL,
    reason TEXT,
    worker_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS embedding_2d (
    post_id TEXT PRIMARY KEY,
    x DOUBLE PRECISION NOT NULL,
    y DOUBLE PRECISION NOT NULL,
    cluster_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_labels (
    cluster_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    keywords TEXT NOT NULL,
    doc_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS narrative_events (
    event_id BIGSERIAL PRIMARY KEY,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    peak_date TEXT NOT NULL,
    peak_anomaly_score DOUBLE PRECISION,
    sentiment_delta DOUBLE PRECISION,
    dominant_subreddits TEXT,
    top_terms TEXT,
    top_post_ids TEXT,
    auto_label TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(timestamp);
CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit);
CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_timestamp ON comments(timestamp);
CREATE INDEX IF NOT EXISTS idx_preprocessed_filtered ON preprocessed(is_filtered);
CREATE INDEX IF NOT EXISTS idx_sentiment_label ON sentiment_predictions(label);
CREATE INDEX IF NOT EXISTS idx_sentiment_logits_gin ON sentiment_predictions USING GIN (logits);
CREATE INDEX IF NOT EXISTS idx_topics_coherence ON topics(coherence_score);
CREATE INDEX IF NOT EXISTS idx_topic_assignments_topic ON topic_assignments(topic_id);
CREATE INDEX IF NOT EXISTS idx_tot_week ON topic_over_time(week_start);
CREATE INDEX IF NOT EXISTS idx_sd_date ON sentiment_daily(date);
CREATE INDEX IF NOT EXISTS idx_tst_date ON topic_sentiment_trends(date);
CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_kind ON analysis_artifacts(kind);
CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_status ON analysis_artifacts(status);
CREATE INDEX IF NOT EXISTS idx_analysis_artifacts_freshness ON analysis_artifacts(freshness_timestamp);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_status ON analysis_runs(status);
CREATE INDEX IF NOT EXISTS idx_events_peak ON narrative_events(peak_date);
CREATE INDEX IF NOT EXISTS idx_emb2d_cluster ON embedding_2d(cluster_id);
CREATE INDEX IF NOT EXISTS idx_batch_collections_subreddit ON batch_collections(subreddit);
CREATE INDEX IF NOT EXISTS idx_batch_collections_timestamp ON batch_collections(collection_timestamp);
