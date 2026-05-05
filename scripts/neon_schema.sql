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
CREATE INDEX IF NOT EXISTS idx_batch_collections_subreddit ON batch_collections(subreddit);
CREATE INDEX IF NOT EXISTS idx_batch_collections_timestamp ON batch_collections(collection_timestamp);
