# Product Requirements Document (PRD)

## Project Title:
**Streaming Reddit-Based Topic Sentiment Analyzer with Drift Detection and Real-Time Dashboard**

---

## 1. Overview

This project builds a real-time text classification system that monitors Reddit threads and comments related to a target domain (e.g., technology, policy, markets), classifies them by sentiment, and surfaces aggregate insights via an interactive dashboard. The system is equipped with drift detection, dynamic topic tracking, and a modular MLOps deployment stack.

Reddit’s active discourse makes it a valuable proxy for public sentiment in domains where real-time feedback is critical. This project operationalizes sentiment modeling in an evolving environment with rich temporal signals and user-generated content.

---

## 2. Objectives

- Stream and classify Reddit posts and comments for domain-specific sentiment.
- Ingest live Reddit data using the Reddit or Pushshift API.
- Monitor shifts in language and sentiment patterns over time.
- Provide a real-time dashboard with filtering, simulation, and analysis capabilities.
- Integrate full MLOps observability using FastAPI, Streamlit, and MLflow.

---

## 3. Problem Statement

Reddit provides a large, high-signal, and freely accessible text corpus across topics and communities. However, tracking meaningful sentiment from Reddit in real time is non-trivial due to topic diversity, slang, and rapidly shifting discourse. A robust system is needed to capture this evolving sentiment, detect drift, and provide an operational tool for analysts, researchers, or strategists.

---

## 4. Scope

- **Classification Task**: Label each Reddit post or comment as:
  - `Positive`
  - `Neutral`
  - `Negative`

- **Streaming Context**:
  - Reddit data is streamed using scheduled API calls or WebSocket proxies.
  - Real-time display and processing of Reddit discussions from selected subreddits or keyword queries.

- **Simulation Capability**:
  - Users can input a Reddit-style comment and receive classification.
  - Topic sliders allow adjustment of input categories (e.g., tech, policy, market).

---

## 5. Data Sources

### 5.1 Live Data (via Reddit API or Pushshift API)

- Targeted subreddits (e.g., `r/technology`, `r/politics`, `r/investing`)
- Keyword-filtered post/comment streams (e.g., "AI", "interest rates", "EVs", "recession")
- Metadata: upvotes, timestamps, subreddit, author karma, etc.

#### API Rate Limiting Strategy
- **Reddit API Limits**: 600 requests per 10 minutes (1 request/second)
- **Implementation**: 
  - Request queue with exponential backoff (1s, 2s, 4s delays)
  - Priority queuing: new posts > comments > historical data
  - Bulk request optimization for comment threads
  - Circuit breaker pattern for API failures
- **Monitoring**: API usage tracking with alerts at 80% threshold
- **Fallback**: Cached data serving during rate limit periods

### 5.2 Labeling Strategy

- **Weak Supervision**:
  - Lexicon-based rules (e.g., sentiment lexicons, VADER, financial dictionaries)
  - Heuristic signals: post score (upvotes), karma, linguistic features

- **Model Bootstrapping**:
  - Fine-tune pretrained sentiment models (e.g., RoBERTa, DistilBERT) on subreddit-specific data

---

## 6. System Components

### 6.1 Data Pipeline

- Reddit API puller (PRAW or custom FastAPI service with scheduled calls)
- Preprocessing: tokenization, lemmatization, cleaning, slang normalization
- Real-time message queue or local cache for streaming

#### Storage Requirements
- **Database**: PostgreSQL for structured data and metadata
  - Reddit posts/comments: ~500KB per 1000 posts
  - User metadata and subreddit information
  - Sentiment classifications with timestamps
  - Model training data and annotations
- **Time-Series Storage**: InfluxDB or TimescaleDB for sentiment trends
  - Real-time sentiment scores by subreddit/keyword
  - Drift detection metrics and alerts
  - API usage and system performance metrics
- **Object Storage**: AWS S3/MinIO for model artifacts and embeddings
  - Model checkpoints and versions (~1-4GB per RoBERTa model)
  - Text embeddings cache (~100MB per 10K posts)
  - Training datasets and evaluation results
- **Caching Layer**: Redis for session state and frequent queries
  - Recent sentiment classifications (24-hour TTL)
  - API response caching for dashboard
  - User session data for Streamlit interface

#### Storage Capacity Planning
- **Initial**: 10GB database, 5GB object storage, 1GB cache
- **6 Months**: 100GB database, 50GB object storage (model versions)
- **1 Year**: 500GB database, 200GB object storage
- **Backup Strategy**: Daily database backups, weekly model artifact snapshots

### 6.2 Feature Engineering

- Textual embeddings (e.g., BERT, Sentence-BERT)
- Sentiment polarity score (VADER baseline + model output)
- Context features: subreddit, author karma, post/comment type
- Time features: hourly/daily activity, trend deviation

---

## 7. Model Architecture

- **Classifier Type**:
  - Baseline: Logistic Regression + TF-IDF + VADER ensemble
  - Production: Fine-tuned RoBERTa or domain-adapted DistilBERT

- **Evaluation Metrics**:
  - F1-score, ROC-AUC, agreement with lexicon-based methods
  - Drift-aware accuracy on time-split validation sets

- **Training Regimen**:
  - Self-labeled Reddit dataset with noise-tolerant learning
  - Option to retrain or adaptively fine-tune weekly on new content

---

## 8. Deployment Stack

### 8.1 Backend API (FastAPI)

- Model inference endpoint:
  - Input: single or batch Reddit texts
  - Output: sentiment class, probability, topic tags
  - API supports continuous ingestion pipeline and logging

### 8.2 Frontend Interface (Streamlit)

- Live Reddit dashboard:
  - Display of current classified Reddit posts
  - Trend plots (sentiment per subreddit, keyword, topic)
  - Custom input simulation (write a post, get sentiment)
  - Filters for subreddit, keyword, time

### 8.3 Experiment Tracking (MLflow)

- Version control for model, preprocessing, and training data
- Confidence tracking across time slices
- Drift detection metric logging and retrain triggers

---

## 9. Monitoring and Drift Detection

- Input drift: Embedding similarity, vocabulary shift
- Output drift: Sentiment distribution changes, entropy increase
- Concept drift: Misalignment between model and current data

- **Tools**:
  - `Evidently` for drift and data quality dashboards
  - `River` for continuous drift detection and alerting

- **Response Actions**:
  - Shadow model comparisons
  - Scheduled retraining and data augmentation from recent posts

---

## 10. System Diagram
```
[Reddit API] → [Rate Limiter] → [Message Queue] → [Preprocessing + Embedding]
                     ↓                                    ↓
              [PostgreSQL] ← [Sentiment Classifier] ← [Model Store]
                     ↓                ↓                     ↓
              [TimescaleDB] → [Drift Monitor] → [MLflow + Logs]
                     ↓                ↓
              [Redis Cache] ← [FastAPI Backend] ↔ [Streamlit Frontend]
```

---

## 11. Project Timeline (4 Weeks)

| Week | Tasks                                                                 |
|------|-----------------------------------------------------------------------|
| 1    | Configure Reddit API access, set up ingestion pipeline, create baseline model |
| 2    | Implement drift monitoring and data labeling strategy, log to MLflow |
| 3    | Build and containerize FastAPI + deploy inference API                 |
| 4    | Launch Streamlit dashboard with simulation + deploy entire stack     |

---

## 12. Deliverables

- **Public GitHub repository**:
  - Clean, modular pipeline for Reddit data ingestion, classification, and visualization
  - Config-driven system with logging and testing
  - Notebooks for labeling and evaluation
  - Docker support for API and dashboard

- **Deployed Live Application**:
  - Hosted on Streamlit Cloud, Hugging Face Spaces, or a custom server

- **README** with setup instructions, architecture, and use cases