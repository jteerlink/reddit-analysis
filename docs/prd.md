# Product Requirements Document (PRD)

## Project Title:
**Offline Reddit-Based Topic & Sentiment Analyzer for Inflation Forecasting**

---

## 1. Overview

This project builds an offline batch-processing ML system that analyzes Reddit discussions related to economic topics (inflation, markets, policy) to extract sentiment trends and identify emerging topics. The system uses scheduled data collection, batch inference, and periodic reporting to provide insights for inflation forecasting and economic sentiment tracking.

Reddit's active discourse provides a valuable proxy for public economic sentiment. This project operationalizes sentiment and topic modeling through an automated batch pipeline with drift detection, topic tracking, and comprehensive reporting - all running locally without requiring real-time infrastructure.

---

## 2. Objectives

- Collect and analyze Reddit posts and comments for economic sentiment patterns.
- Ingest historical and recent Reddit data using scheduled batch collection.
- Identify trending topics and track their evolution over time.
- Monitor shifts in sentiment distributions and detect significant changes.
- Generate periodic reports with visualizations and insights.
- Maintain full MLOps traceability using local MLflow tracking.

---

## 3. Problem Statement

Reddit provides a large, high-signal, and freely accessible text corpus that reflects real-time public sentiment on economic issues. Traditional economic indicators lag by weeks or months, making it difficult to capture emerging sentiment shifts. An automated offline system is needed to periodically analyze Reddit discussions, extract sentiment patterns, identify trending topics, and generate actionable insights for economic forecasting - without requiring complex real-time infrastructure or continuous monitoring.

---

## 4. Scope

### 4.1 Core ML Components

1. **Sentiment Analysis**: Classify each Reddit post/comment as:
   - `Positive`
   - `Neutral`
   - `Negative`
   - Include confidence scores for filtering low-certainty predictions

2. **Topic Discovery**: Identify and track trending topics using contextual topic modeling
   - Extract dominant themes from discussions
   - Track topic evolution over time
   - Detect emerging topics before they peak

3. **Time Series Analysis**: Analyze sentiment trends and patterns
   - Daily/weekly sentiment aggregations
   - Moving averages and trend detection
   - Change point detection for sentiment shifts
   - Correlation with economic indicators (optional)

### 4.2 Processing Model

- **Batch Processing**: Scheduled daily/weekly collection and analysis runs
- **Historical Analysis**: Analyze past 90-180 days for baseline and training
- **Incremental Updates**: Process only new data since last run
- **Offline Execution**: All processing runs locally, no live services required

---

## 5. Data Sources

### 5.1 Reddit Data Collection (Batch)

**Target Subreddits** (Economic/Financial Focus):
- `r/Economics`, `r/economy`, `r/investing`
- `r/personalfinance`, `r/StockMarket`
- `r/technology` (for tech-related economic impact)
- Additional subreddits configurable via `.env`

**Target Keywords**:
- Inflation-related: "inflation", "CPI", "prices", "cost of living"
- Monetary policy: "Fed", "interest rates", "rate hikes", "Powell"
- Economic indicators: "recession", "unemployment", "GDP", "jobs"
- Market sentiment: "bull market", "bear market", "crash", "rally"

**Metadata Collected**:
- Post/comment text, title
- Timestamps (for time series analysis)
- Upvotes (signal of agreement/importance)
- Subreddit, author karma
- Comment threads (for context)

### 5.2 Collection Schedule

- **Historical Backfill**: One-time collection of past 90-180 days
- **Daily Collection**: Automated collection of previous day's data
- **API Rate Limiting**: 
  - Respects 600 requests/10 min limit (existing implementation ✅)
  - Exponential backoff and circuit breaker (existing ✅)
  - Runs during off-peak hours to minimize impact

### 5.3 Labeling Strategy

**Phase 1: Weak Supervision (Automated)**
- **VADER Sentiment**: Baseline labels for all posts/comments
- **Lexicon-based Rules**:
  - Financial sentiment dictionaries (FinBERT lexicon)
  - Economic indicator keywords (positive/negative associations)
- **Heuristic Signals**:
  - High upvotes + positive language → Positive label
  - Downvoted + negative language → Negative label
  - Filter: Only use high-confidence weak labels (VADER score > 0.5 or < -0.5)

**Phase 2: Model Training**
- Fine-tune DistilBERT on weakly labeled dataset
- Validation: Manual review of 500-1000 predictions
- Active learning: Human label uncertain predictions for retraining

---

## 6. System Components

### 6.1 Data Collection Pipeline (Existing ✅)

**Implementation**: Already built and functional
- Reddit API client with PRAW (existing)
- Rate limiting with circuit breaker (existing)
- Historical collection scripts (existing)
- SQLite storage with optimized schema (existing)

**Usage**: Scheduled via cron for daily/weekly runs

### 6.2 Preprocessing Pipeline (New)

**Text Cleaning**:
- Remove URLs, special characters, excessive whitespace
- Expand contractions and normalize slang
- Handle Reddit-specific formatting (markdown, quotes)
- Filter out bot accounts and automated posts

**Tokenization & Normalization**:
- Lowercase conversion
- Lemmatization (spaCy)
- Stop word removal (optional, context-dependent)

**Embedding Generation**:
- Sentence-level embeddings using `sentence-transformers`
- Cache embeddings to avoid recomputation
- Used for topic modeling and similarity analysis

### 6.3 Storage Architecture (Simplified)

**Primary Database: SQLite** (existing ✅)
- Posts and comments (~500KB per 1000 posts)
- Sentiment predictions with confidence scores
- Topic assignments and keywords
- API metrics and collection metadata
- **Size Planning**: 
  - 90 days: ~50MB
  - 1 year: ~500MB-1GB
  - 5 years: ~5GB

**Model Storage: Local Filesystem**
- Model checkpoints: `models/sentiment/`
- Topic models: `models/topics/`
- Embeddings cache: `cache/embeddings/`
- MLflow artifacts: `mlruns/`
- **Size Planning**: ~2-5GB total

**Exports & Reports**:
- JSON exports for external analysis
- CSV files for time series data
- HTML reports with visualizations
- Jupyter notebooks for ad-hoc analysis

**No Requirements For**:
- ❌ PostgreSQL/TimescaleDB
- ❌ Redis caching layer
- ❌ S3/cloud storage
- ❌ Message queues

### 6.4 Feature Engineering

**Text Features**:
- DistilBERT embeddings (768-dimensional)
- TF-IDF vectors (for baseline models)
- VADER sentiment scores (weak labels)

**Contextual Features**:
- Subreddit (categorical encoding)
- Author karma (log-scaled)
- Post vs. comment indicator
- Comment depth in thread

**Temporal Features**:
- Day of week (weekday vs. weekend patterns)
- Hour of day (activity patterns)
- Days since account creation
- Posting frequency (author-level)

**Topic Features** (from BERTopic):
- Topic assignment (categorical)
- Topic probability distribution
- Topic coherence scores

---

## 7. Model Architecture

### 7.1 Sentiment Analysis (DistilBERT)

**Model**: `distilbert-base-uncased` fine-tuned for 3-class sentiment

**Architecture**:
```
Input Text → DistilBERT Tokenizer → DistilBERT Encoder (66M params)
           → Dropout(0.1) → Linear(768 → 3) → Softmax
           → Output: [P(Positive), P(Neutral), P(Negative)]
```

**Training Strategy**:
- **Phase 1 - Weak Supervision**:
  - Generate labels using VADER + heuristics
  - Filter for high-confidence labels (|score| > 0.5)
  - Train on ~50k weakly labeled posts/comments
  
- **Phase 2 - Fine-tuning**:
  - Initial training: 3 epochs, batch size 32
  - Learning rate: 2e-5 with warmup
  - Class balancing: Weighted loss or oversampling
  
- **Phase 3 - Active Learning** (optional):
  - Manual label uncertain predictions (confidence < 0.7)
  - Retrain with 500-1000 human-labeled examples
  - Iteratively improve on edge cases

**Evaluation Metrics**:
- F1-score (macro and per-class)
- ROC-AUC for multi-class
- Confusion matrix analysis
- Agreement with VADER baseline (Pearson correlation)
- Time-stratified validation (train on old, test on recent)

**Inference**:
- Batch inference on new data (1000s of posts per minute)
- Store predictions with confidence scores
- Flag low-confidence predictions for review

### 7.2 Topic Modeling (BERTopic)

**Model**: BERTopic with temporal tracking

**Architecture**:
```
Input Texts → Sentence-BERT Embeddings
           → UMAP Dimensionality Reduction
           → HDBSCAN Clustering
           → c-TF-IDF Topic Representation
           → Named Topics (e.g., "inflation_concerns")
```

**Configuration**:
- Embedding model: `all-MiniLM-L6-v2` (fast, 22M params)
- Min topic size: 30 posts
- Max topics: 50-100 (configurable)
- Topic diversity: 0.5 (balanced specificity)

**Temporal Topics**:
- Track topic evolution over time
- Detect emerging topics (new clusters)
- Monitor topic decline (shrinking clusters)
- Time-sliced topic modeling (weekly/monthly)

**Topic Labeling**:
- Automatic: Top-N keywords via c-TF-IDF
- LLM-assisted: Use GPT/Claude to generate topic names (optional)
- Manual: Human curation of important topics

**Output**:
- Topic assignments for each post
- Topic keywords and representative documents
- Topic-over-time visualizations
- Topic coherence scores

### 7.3 Time Series Analysis

**Approach**: Statistical methods + Prophet for forecasting

**Components**:

1. **Sentiment Aggregation**:
   - Daily average sentiment score by subreddit
   - Weighted by upvotes (importance weighting)
   - 7-day and 30-day moving averages
   - Sentiment volatility (standard deviation)

2. **Trend Detection**:
   - Change point detection (PELT algorithm)
   - Identify significant sentiment shifts
   - Alert when sentiment crosses thresholds
   - Compare to historical baselines

3. **Forecasting** (Facebook Prophet):
   ```python
   Prophet(
       daily_seasonality=True,
       weekly_seasonality=True,
       changepoint_prior_scale=0.05  # Flexible trend
   )
   ```
   - Forecast next 7-14 days of sentiment
   - Generate confidence intervals
   - Compare predictions to actual (model validation)

4. **Topic-Specific Trends**:
   - Track sentiment for each topic over time
   - Identify topics with strongest sentiment changes
   - Correlate topic volume with sentiment shifts

**Visualization**:
- Time series plots with trend lines
- Moving average overlays
- Change point annotations
- Forecast plots with confidence bands

### 7.4 Model Management

**Versioning** (MLflow):
- Track all model versions with metadata
- Log hyperparameters, metrics, artifacts
- Easy rollback to previous versions
- A/B testing of model variants

**Retraining Schedule**:
- Initial training: One-time on historical data
- Incremental updates: Monthly with new data
- Triggered retraining: When drift detected (>10% performance drop)

**Model Artifacts**:
- Sentiment model: `models/sentiment/distilbert_v{version}.pt`
- Topic model: `models/topics/bertopic_v{version}.pkl`
- Time series models: `models/timeseries/prophet_v{version}.json`

---

## 8. Execution Architecture

### 8.1 Batch Processing Pipeline

**Daily Workflow** (Automated via Cron):
```bash
# 1. Data Collection (2 AM daily)
python scripts/collect-historical.py --days-back 1

# 2. Preprocessing (2:30 AM)
python scripts/preprocess_batch.py --new-only

# 3. Sentiment Inference (3 AM)
python scripts/batch_sentiment.py --batch-size 1000

# 4. Topic Modeling (3:30 AM)
python scripts/update_topics.py --incremental

# 5. Time Series Analysis (4 AM)
python scripts/analyze_trends.py --window 90days

# 6. Drift Detection (4:30 AM)
python scripts/detect_drift.py --weekly

# 7. Generate Summary & Notify (5 AM)
python scripts/notify.py --email --slack

# On-demand: Launch Streamlit dashboard to explore results
# streamlit run app.py
```

**Weekly Workflow**:
- Retrain topic model on full dataset
- Perform drift detection analysis
- Generate comprehensive weekly report
- Archive old data (optional compression)

**Monthly Workflow**:
- Evaluate model performance on recent data
- Retrain sentiment model if drift detected
- Generate monthly trend analysis
- Backup database and models

### 8.2 Command-Line Interface

**Unified CLI** (`reddit-analyzer`):
```bash
# Data collection
reddit-analyzer collect --days 1
reddit-analyzer collect --range 2024-01-01:2024-01-31

# Model training
reddit-analyzer train sentiment --epochs 3
reddit-analyzer train topics --min-size 30

# Inference
reddit-analyzer predict --input data/new_posts.json
reddit-analyzer analyze-trends --days 30

# Dashboard
reddit-analyzer dashboard  # Launch Streamlit app
streamlit run app.py       # Direct launch

# Notifications
reddit-analyzer notify --email user@example.com
reddit-analyzer notify --slack --channel #economics

# Utilities
reddit-analyzer stats
reddit-analyzer export --format csv --output data.csv
```

### 8.3 Visualization Dashboard (Streamlit)

**Interactive Dashboard** (`streamlit run app.py`):
- Launch on-demand to explore latest data
- Reads directly from SQLite database
- Interactive filtering and date range selection
- Real-time chart updates as you explore

**Dashboard Sections**:

1. **Overview Tab**:
   - Key metrics cards (posts collected, sentiment distribution)
   - Sentiment gauge (overall positive/neutral/negative ratio)
   - Top 5 trending topics with sentiment
   - Recent anomalies or notable shifts
   - Last collection timestamp

2. **Sentiment Analysis Tab**:
   - Time series plot with date range selector
   - Moving average overlays (7-day, 30-day)
   - Subreddit comparison (multi-line chart)
   - Sentiment distribution histogram
   - Change point markers on timeline
   - Forecast visualization (Prophet predictions)

3. **Topic Explorer Tab**:
   - Topic list with keywords and doc counts
   - Topic-over-time heatmap
   - Drill-down: Click topic to see posts
   - Word clouds for each topic
   - Topic sentiment breakdown
   - Emerging topics highlight (new in last 7 days)

4. **Deep Dive Tab**:
   - Search posts by keyword/subreddit/date
   - Individual post viewer with predictions
   - Confidence score filtering
   - Export filtered data (CSV/JSON)
   - Topic-specific sentiment trends
   - Subreddit-specific analysis

5. **Model Performance Tab**:
   - Drift detection metrics
   - Model confidence distribution
   - Prediction examples (high/low confidence)
   - VADER vs. model agreement chart
   - Recent model retraining history
   - MLflow metrics integration

6. **Data Quality Tab**:
   - Collection statistics
   - Posts per day chart
   - API usage metrics
   - Data quality warnings
   - Database size and growth

**Visualization Libraries**:
- `plotly` for interactive charts
- `streamlit` for dashboard framework
- `wordcloud` for topic visualization
- `altair` for advanced visualizations (optional)

**Usage Patterns**:
- **On-demand**: Launch when you want to explore data
- **Scheduled screenshots**: Auto-capture dashboard views (optional)
- **Presentation mode**: Full-screen for meetings
- **Export**: Download charts as PNG/SVG from Streamlit

**Deployment Options**:
- **Local**: `streamlit run app.py` (default)
- **Network**: `streamlit run app.py --server.address 0.0.0.0` (access from other devices)
- **Streamlit Cloud**: Deploy for remote access (optional)

**Notification System** (Separate from Dashboard):
- Automated summary emails with key metrics
- Slack messages for critical alerts (sentiment spikes, drift warnings)
- Generated via separate script, not through Streamlit

### 8.4 Experiment Tracking (MLflow)

**Local MLflow Setup**:
- Tracking server: `http://localhost:5000`
- Artifact storage: `file://mlruns/`
- Backend database: `sqlite:///mlflow.db`

**Tracked Experiments**:
- Sentiment model training runs
- Topic model configurations
- Hyperparameter tuning results
- Model evaluation metrics

**Logged Information**:
- Parameters: learning rate, batch size, model config
- Metrics: F1, accuracy, training loss
- Artifacts: model checkpoints, confusion matrices
- Tags: data version, training date, purpose

**Model Registry**:
- Production models: Tagged as "production"
- Staging models: Tagged as "staging" for testing
- Archived models: Keep for reproducibility

### 8.5 Development Environment

**Interactive Analysis** (Jupyter):
- `notebooks/explore_data.ipynb` - Data exploration
- `notebooks/train_sentiment.ipynb` - Model training
- `notebooks/analyze_topics.ipynb` - Topic analysis
- `notebooks/trend_analysis.ipynb` - Time series exploration

**Testing**:
- Unit tests: `tests/` directory
- Integration tests: End-to-end pipeline validation
- CI: GitHub Actions for automated testing (optional)

---

## 9. Drift Detection & Monitoring

### 9.1 Drift Types

**Input Drift** (Data Distribution Changes):
- Vocabulary shifts (new slang, terminology)
- Topic distribution changes (new discussions)
- Subreddit activity patterns
- Post length and complexity changes

**Output Drift** (Model Performance Degradation):
- Sentiment distribution changes (more negative/positive)
- Prediction confidence decline
- Disagreement with VADER baseline increasing
- Accuracy drop on validation set

**Concept Drift** (Relationship Changes):
- Same words now mean different things
- Sarcasm and irony usage shifts
- Community-specific language evolution

### 9.2 Detection Methods

**Weekly Drift Analysis**:

1. **Statistical Tests**:
   - KS test for distribution comparison (current vs. baseline)
   - Chi-square test for sentiment distribution
   - Jensen-Shannon divergence for topic distributions

2. **Embedding Similarity**:
   - Compare average embeddings (current week vs. baseline)
   - Cosine similarity threshold: Alert if < 0.85
   - Track vocabulary novelty rate

3. **Model Performance**:
   - Evaluate on recent data with manual labels (sample 200 posts)
   - Compare F1-score to baseline (alert if drops >10%)
   - Track prediction confidence distribution

4. **Topic Coherence**:
   - Monitor topic quality scores
   - Detect if topics becoming incoherent
   - Alert on significant new topic emergence

**Tools**:
- `Evidently` for drift reports (HTML dashboards)
- Custom Python scripts for statistical tests
- MLflow for metric tracking over time

### 9.3 Monitoring Dashboard

**Weekly Drift Report** (Automated):
```
Drift Detection Report - Week of 2024-01-15
===========================================

Input Drift:
✅ Vocabulary similarity: 0.92 (OK)
⚠️  Topic distribution: 0.78 (MODERATE DRIFT)
✅ Post length distribution: 0.94 (OK)

Output Drift:
✅ Sentiment distribution: 0.88 (OK)
⚠️  Prediction confidence: 0.81 avg (DECLINING)
✅ VADER agreement: 0.76 (OK)

Model Performance:
⚠️  Validation F1: 0.72 (down from 0.78 - RETRAIN RECOMMENDED)

Recommendations:
- Consider retraining sentiment model with recent data
- New topic detected: "AI_regulation" (20% of posts)
- Prediction confidence declining - add more training data
```

### 9.4 Response Actions

**Automatic Actions**:
- Log all drift metrics to MLflow
- Generate drift report (HTML + email)
- Alert if thresholds exceeded (email/Slack)
- Archive current model before retraining

**Manual Actions** (Triggered by alerts):
- Review drift report and visualizations
- Decide on retraining necessity
- Collect additional manual labels if needed
- Update model and deploy new version

**Retraining Triggers**:
- F1-score drops > 10% from baseline
- Prediction confidence drops < 0.75 average
- Major topic distribution shift (JSD > 0.3)
- Monthly scheduled retrain regardless of drift

### 9.5 Data Quality Monitoring

**Collection Metrics** (Tracked daily):
- Posts collected per subreddit
- API errors and rate limit hits
- Duplicate posts filtered
- Processing failures

**Data Quality Checks**:
- Text length distribution (flag unusually short/long)
- Language detection (flag non-English)
- Bot account filtering
- Spam/promotional content detection

**Storage Monitoring**:
- Database size growth rate
- Disk space alerts (< 10GB free)
- Backup success verification

---

## 10. System Architecture

### Offline Batch Processing Flow

```
┌─────────────────────────────────────────────────────────────┐
│                   SCHEDULED COLLECTION                       │
│  (Cron: Daily 2 AM)                                         │
│                                                              │
│  [Reddit API] → [Rate Limiter] → [SQLite Database]         │
│       ↑               ↑                    ↓                 │
│   (PRAW)      (Circuit Breaker)    [Raw Posts/Comments]    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  PREPROCESSING PIPELINE                      │
│  (Cron: Daily 2:30 AM)                                      │
│                                                              │
│  [Text Cleaning] → [Tokenization] → [Embedding Generation] │
│                                              ↓               │
│                                    [Embeddings Cache]       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    ML INFERENCE BATCH                        │
│  (Cron: Daily 3 AM)                                         │
│                                                              │
│  ┌─────────────────┐    ┌──────────────────┐               │
│  │  DistilBERT     │    │    BERTopic      │               │
│  │  Sentiment      │    │  Topic Modeling  │               │
│  │  Classifier     │    │                  │               │
│  └────────┬────────┘    └────────┬─────────┘               │
│           │                      │                          │
│           ▼                      ▼                          │
│  [Sentiment Scores]      [Topic Assignments]               │
│           │                      │                          │
│           └──────────┬───────────┘                          │
│                      ▼                                      │
│            [SQLite: predictions table]                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 TIME SERIES ANALYSIS                         │
│  (Cron: Daily 4 AM)                                         │
│                                                              │
│  [Aggregation] → [Trend Detection] → [Prophet Forecast]    │
│        ↓                  ↓                    ↓             │
│  [Daily Metrics]   [Change Points]    [7-day Forecast]     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 DRIFT DETECTION & ALERTS                     │
│  (Cron: Daily 4:30 AM)                                      │
│                                                              │
│  [Drift Analysis] → [Alert Generation] → [Email/Slack]     │
│                                                              │
│  - Performance degradation warnings                         │
│  - Significant sentiment shifts                             │
│  - New topic emergence alerts                               │
│  - Data quality issues                                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              STREAMLIT DASHBOARD (On-Demand)                 │
│                                                              │
│  [SQLite DB] → [Streamlit App] → [Interactive Visualizations]│
│                                                              │
│  - Sentiment trends (time series, forecasts)                │
│  - Topic explorer (word clouds, evolution)                  │
│  - Deep dive (search, filter, export)                       │
│  - Model performance metrics                                │
│  - Drift detection dashboards                               │
│                                                              │
│  Launch: streamlit run app.py                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  EXPERIMENT TRACKING                         │
│                    (MLflow Local)                           │
│                                                              │
│  [Model Versions] ← [Training Runs] → [Metrics Logging]    │
│         ↓                                         ↓          │
│  [Model Registry]                         [Drift Detection] │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              MANUAL ANALYSIS (As Needed)                     │
│                                                              │
│  [Jupyter Notebooks] ← [SQLite + Models] → [Ad-hoc Reports]│
└─────────────────────────────────────────────────────────────┘
```

---

## 11. Implementation Timeline (6 Weeks)

### Week 1: Data Foundation
**Goal**: Establish data pipeline and baseline labeling

- [x] Reddit data collection (EXISTING - already functional ✅)
- [ ] Preprocessing pipeline (text cleaning, tokenization)
- [ ] Weak supervision labeling (VADER + heuristics)
- [ ] Generate 50k labeled training dataset
- [ ] Exploratory data analysis notebook
- [ ] Setup MLflow for experiment tracking

**Deliverables**:
- Preprocessed dataset with weak labels
- EDA notebook with insights
- MLflow configured and running

### Week 2: Sentiment Model
**Goal**: Train and validate sentiment classifier

- [ ] Implement DistilBERT fine-tuning pipeline
- [ ] Train on weakly labeled data (3 epochs)
- [ ] Evaluate on validation set (manual labels)
- [ ] Hyperparameter tuning (learning rate, batch size)
- [ ] Batch inference script for new data
- [ ] Log all experiments to MLflow

**Deliverables**:
- Trained sentiment model (F1 > 0.70)
- Batch inference script
- Model evaluation report

### Week 3: Topic Modeling
**Goal**: Implement and configure BERTopic

- [ ] Setup BERTopic with sentence-transformers
- [ ] Train on historical data (90 days)
- [ ] Generate topic labels and keywords
- [ ] Implement temporal topic tracking
- [ ] Topic visualization dashboards
- [ ] Integrate with sentiment pipeline

**Deliverables**:
- Trained topic model
- Topic labels and descriptions
- Topic-over-time visualizations

### Week 4: Time Series Analysis
**Goal**: Build trend analysis and forecasting

- [ ] Daily sentiment aggregation pipeline
- [ ] Moving average calculations (7-day, 30-day)
- [ ] Change point detection implementation
- [ ] Prophet forecasting setup
- [ ] Topic-specific trend tracking
- [ ] Correlation analysis with economic indicators (optional)

**Deliverables**:
- Time series analysis scripts
- Forecast generation pipeline
- Trend visualization notebooks

### Week 5: Automation & Visualization
**Goal**: Complete end-to-end automation and interactive dashboard

- [ ] Cron job configuration for daily pipeline
- [ ] Streamlit dashboard development (all tabs)
- [ ] Interactive charts and filters
- [ ] Email/Slack notification system
- [ ] Error handling and logging
- [ ] Documentation and README updates

**Deliverables**:
- Fully automated daily pipeline
- Interactive Streamlit dashboard
- Notification system

### Week 6: Drift Detection & Polish
**Goal**: Production-ready system

- [ ] Implement comprehensive drift detection
- [ ] Weekly drift reports with Evidently
- [ ] Automated retraining triggers
- [ ] Model versioning and rollback procedures
- [ ] Performance optimization
- [ ] Final testing and validation
- [ ] Complete documentation

**Deliverables**:
- Production-ready system
- Drift detection dashboards
- Complete documentation
- Deployment guide

---

## 12. Deliverables

### 12.1 Core System Components

**Data Collection** (✅ Already Complete):
- Reddit API client with rate limiting
- Historical and incremental collection scripts
- SQLite database with optimized schema

**ML Pipeline** (To Build):
- Preprocessing scripts for text cleaning and embedding
- DistilBERT sentiment classifier (fine-tuned)
- BERTopic topic modeling system
- Time series analysis with Prophet forecasting
- Batch inference scripts

**Automation**:
- Cron job configurations for scheduled runs
- Error handling and logging
- Automated report generation
- Email/Slack notifications

**Monitoring**:
- Drift detection system (Evidently)
- Model performance tracking (MLflow)
- Data quality monitoring
- Weekly drift reports

### 12.2 Documentation

**Technical Documentation**:
- `README.md` - Setup and usage instructions
- `docs/prd.md` - This document (✅)
- `docs/api-reference.md` - Python API documentation
- `docs/deployment-guide.md` - Production deployment
- `docs/model-training.md` - Model training procedures

**Analysis Notebooks**:
- `notebooks/01_data_exploration.ipynb` - EDA
- `notebooks/02_sentiment_training.ipynb` - Model training
- `notebooks/03_topic_analysis.ipynb` - Topic modeling
- `notebooks/04_time_series.ipynb` - Trend analysis
- `notebooks/05_drift_analysis.ipynb` - Drift detection

### 12.3 Visualization & Outputs

**Streamlit Dashboard** (`app.py`):
- Interactive sentiment trends with date range filtering
- Topic explorer with word clouds and evolution charts
- Deep dive interface for searching and filtering posts
- Model performance and drift detection metrics
- Data quality monitoring
- Export capabilities (CSV, JSON, PNG charts)

**Automated Notifications**:
- Daily summary emails (key metrics, top topics)
- Slack alerts for significant events:
  - Major sentiment shifts (>20% change)
  - New trending topics detected
  - Drift warnings (model performance degradation)
  - Data collection failures

**Analysis Notebooks** (Ad-hoc deep dives):
- Monthly comprehensive analysis
- Model evaluation and retraining reports
- Correlation with economic indicators
- Custom research queries

### 12.4 Model Artifacts

**Trained Models** (in `models/` directory):
- Sentiment classifier: `sentiment/distilbert_v{version}.pt`
- Topic model: `topics/bertopic_v{version}.pkl`
- Time series models: `timeseries/prophet_v{version}.json`

**MLflow Registry**:
- All model versions with metadata
- Experiment tracking logs
- Performance metrics history
- Model comparison reports

### 12.5 Data Exports

**Available Formats**:
- CSV: Time series data, sentiment scores
- JSON: Full post/comment data with predictions
- Parquet: Efficient storage for large datasets
- HTML: Interactive reports with visualizations

**Export Scripts**:
- `scripts/export_sentiment_trends.py`
- `scripts/export_topics.py`
- `scripts/export_for_analysis.py`

### 12.6 Testing & Quality

**Test Suite**:
- Unit tests for preprocessing functions
- Integration tests for pipeline components
- Model evaluation scripts
- Data quality validation

**CI/CD** (Optional):
- GitHub Actions for automated testing
- Pre-commit hooks for code quality
- Automated model evaluation on PR

### 12.7 Deployment Package

**Repository Structure**:
```
reddit-analyzer/
├── app.py                   # Streamlit dashboard (main entry point)
├── src/reddit_api/          # Data collection (existing ✅)
├── src/ml/                  # ML pipeline (new)
│   ├── preprocessing.py
│   ├── sentiment.py
│   ├── topics.py
│   └── timeseries.py
├── src/dashboard/           # Streamlit components (new)
│   ├── overview.py          # Overview tab
│   ├── sentiment.py         # Sentiment analysis tab
│   ├── topics.py            # Topic explorer tab
│   ├── deepdive.py          # Deep dive tab
│   ├── performance.py       # Model performance tab
│   └── utils.py             # Shared utilities
├── scripts/                 # Automation scripts
│   ├── batch_inference.py
│   ├── train_models.py
│   ├── notify.py            # Email/Slack alerts
│   └── detect_drift.py
├── notebooks/               # Analysis notebooks
├── models/                  # Trained models
├── tests/                   # Test suite
├── docs/                    # Documentation
├── .env.example            # Configuration template
├── pyproject.toml          # Dependencies
└── README.md               # Setup instructions
```

**Installation Package**:
- One-command setup script
- Virtual environment configuration
- Dependency management via uv
- Configuration wizard

### 12.8 Success Criteria

**Technical Metrics**:
- ✅ Sentiment model F1-score > 0.70
- ✅ Topic coherence score > 0.50
- ✅ Daily pipeline completes in < 30 minutes
- ✅ Drift detection runs weekly without errors
- ✅ Reports generated automatically

**Business Metrics**:
- Identify sentiment trends 1-2 weeks before economic indicators
- Track 20-30 coherent topics related to inflation/economy
- Generate actionable insights in daily reports
- Detect significant sentiment shifts within 24 hours

**Operational Metrics**:
- 99% pipeline success rate
- < 5% false positive drift alerts
- Model retraining required < monthly
- Zero data loss or corruption

---

## 13. Future Enhancements

**Phase 2 Additions** (Post-MVP):
- Multi-language support (Spanish, French economic discussions)
- Integration with Twitter/X data
- Real-time streaming mode (optional upgrade from batch)
- Correlation analysis with actual inflation data
- Predictive models for economic indicators
- REST API endpoint for external tools (optional)
- Streamlit Cloud deployment for remote access
- Mobile notifications for critical alerts
- Advanced dashboard features (custom date ranges, saved views)

**Advanced Analytics**:
- Causal inference (do certain topics drive sentiment?)
- Network analysis (information diffusion patterns)
- User segmentation (retail vs. professional sentiment)
- Cross-platform sentiment comparison

**Infrastructure**:
- Docker containerization
- Cloud deployment option (AWS/GCP)
- PostgreSQL upgrade for production scale
- Distributed processing for large datasets