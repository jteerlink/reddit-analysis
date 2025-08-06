# Reddit API Data Collection Module

A comprehensive Python module for collecting Reddit data with rate limiting, circuit breaker patterns, and persistent storage. Originally developed as part of the inflation forecasting project for sentiment analysis on social media discourse.

## 🚀 Features

- **Rate-Limited API Access**: Respects Reddit's 600 requests/10-minute limit
- **Circuit Breaker Pattern**: Fault-tolerant with automatic recovery
- **Exponential Backoff**: Intelligent retry logic for failed requests  
- **Persistent Storage**: SQLite database with optimized schema
- **Keyword Filtering**: Collect posts/comments matching specific terms
- **Comprehensive Metrics**: API usage tracking and performance monitoring
- **Export Capabilities**: JSON export for downstream processing
- **CLI Interface**: Command-line tool for easy data collection

## 📦 Installation

### Quick Setup with uv (Recommended)
```bash
# Clone repository
git clone https://github.com/your-username/inflation-forcasting.git
cd inflation-forcasting

# Run automated setup script
./scripts/dev-setup.sh

# Or manual uv setup:
uv venv
source .venv/bin/activate  # Linux/Mac
uv pip install -e ".[dev,ml]"
```

### Alternative: Traditional pip
```bash
# Install in development mode
pip install -e .

# Or install with extras
pip install -e ".[dev,ml]"
```

### Requirements
- Python 3.8+
- Reddit API credentials (free)
- uv package manager (recommended) or pip
- See `pyproject.toml` for full dependency list

## 🔧 Quick Setup

1. **Get Reddit API Credentials**:
   - Go to https://www.reddit.com/prefs/apps
   - Click "Create App" → Choose "script" type
   - Copy your client ID and secret

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Test Authentication**:
   ```bash
   # Using uv
   uv run python -m reddit_api.cli test
   
   # Or traditional Python
   python -m reddit_api.cli test
   ```

## 💻 Usage Examples

### Basic Usage
```python
from reddit_api import RedditConfig, RedditDataCollector, RedditDataStorage

# Create configuration
config = RedditConfig(
    client_id="your_client_id",
    client_secret="your_client_secret", 
    user_agent="YourApp:v1.0 (by /u/yourusername)",
    target_subreddits=['technology', 'MachineLearning'],
    target_keywords=['AI', 'machine learning']
)

# Collect data
collector = RedditDataCollector(config)
posts = collector.collect_subreddit_posts('technology', limit=10)

# Store data
storage = RedditDataStorage('reddit_data.db')
storage.store_posts(posts)
```

### Using Environment Variables
```python
from reddit_api import create_config_from_env, collect_reddit_data

# Load config from .env file
config = create_config_from_env()

# Collect and store data automatically
results = collect_reddit_data(
    config=config,
    posts_per_subreddit=5,
    comments_per_post=10
)
```

### Command Line Interface
```bash
# Using uv (recommended)
uv run reddit-collector test
uv run reddit-collector collect --posts 10 --comments 5
uv run reddit-collector export data.json
uv run reddit-collector stats

# Or direct execution
reddit-collector test
reddit-collector collect --posts 10 --comments 5
reddit-collector export data.json
reddit-collector stats
```

### Advanced Data Analysis
```python
from reddit_api import RedditDataStorage

storage = RedditDataStorage('reddit_data.db')

# Query with filters
tech_posts = storage.query_posts(
    subreddit='technology', 
    keywords=['AI', 'machine learning'],
    limit=100
)

# Get subreddit statistics
stats = storage.get_subreddit_stats()
print(stats)

# Export data
storage.export_to_json('export.json')
```

## 📁 Module Structure

```
src/reddit_api/
├── __init__.py          # Main module exports
├── models.py            # Data models and configuration
├── client.py            # Rate-limited Reddit client
├── collector.py         # Data collection logic
├── storage.py           # Database operations
├── main.py              # High-level orchestration
└── cli.py               # Command-line interface
```

## 🏗️ Architecture

### Core Components

1. **RedditConfig**: Configuration management with sensible defaults
2. **RateLimitedRedditClient**: PRAW wrapper with rate limiting and circuit breaker
3. **RedditDataCollector**: High-level data collection with filtering
4. **RedditDataStorage**: SQLite persistence with query capabilities

### Key Features

- **Rate Limiting**: 600 requests per 10-minute window with queue management
- **Circuit Breaker**: Auto-disable after 5 consecutive failures  
- **Exponential Backoff**: 1s → 2s → 4s → 8s → 60s delays
- **Read-Only Mode**: Uses client credentials only (no username/password)
- **Keyword Filtering**: Case-insensitive matching in titles and content
- **Duplicate Handling**: INSERT OR REPLACE prevents duplicate storage

### Database Schema

**Posts Table**:
- id, title, content, upvotes, timestamp
- subreddit, author, author_karma
- url, num_comments, content_type

**Comments Table**:  
- id, parent_id, content, upvotes, timestamp
- subreddit, author, author_karma, post_id

**API Metrics Table**:
- requests_made, requests_failed, rate_limit_hits
- circuit_breaker_trips, timestamp

## 📊 Performance Characteristics

- **Rate Limiting**: Respects 1 request/second Reddit API limit
- **Storage Efficiency**: ~500KB per 1000 posts (as per PRD)
- **Error Recovery**: Exponential backoff with circuit breaker
- **Memory Usage**: Streaming processing, minimal memory footprint

## 🧪 Testing

```bash
# Run example usage
uv run python example_usage.py

# Test authentication
uv run python -c "from reddit_api import create_config_from_env, test_reddit_connection; print(test_reddit_connection(create_config_from_env()))"

# CLI tests
uv run reddit-collector test --subreddit test
uv run reddit-collector collect --posts 2 --comments 0
uv run reddit-collector stats

# Development testing
uv run pytest                    # Run test suite
uv run pytest --cov=reddit_api  # With coverage
```

## 📚 UV Package Manager

This project uses [uv](https://github.com/astral-sh/uv) for fast, reliable Python package management.

### Key Benefits
- **Fast**: 10-100x faster than pip for dependency resolution
- **Reliable**: Lockfile ensures reproducible installs
- **Compatible**: Drop-in replacement for pip
- **Modern**: Built-in virtual environment management

### Common UV Commands
```bash
# Development setup
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,ml]"

# Add new dependencies
uv add requests>=2.30.0
uv add --dev pytest>=7.0.0

# Update dependencies
uv lock --upgrade

# Production install
uv pip sync uv.lock
```

See `scripts/uv-commands.md` for complete command reference.

## 🔒 Security & Privacy

- **Read-Only Access**: Only collects publicly available data
- **No User Auth**: Uses application credentials only  
- **Rate Limiting**: Respects Reddit's API terms of service
- **Local Storage**: Data stored locally in SQLite
- **No Secrets in Code**: Credentials loaded from environment

## 📈 Production Considerations

For production deployment, consider:

1. **Database**: Move to PostgreSQL/TimescaleDB
2. **Monitoring**: Add comprehensive metrics and alerting  
3. **Caching**: Implement Redis for session state
4. **Scaling**: Horizontal scaling with load balancing
5. **Security**: Secrets management and API authentication

## 🤝 Integration

### Sentiment Analysis Pipeline
```python
from reddit_api import collect_reddit_data
from your_sentiment_model import analyze_sentiment

# Collect data
results = collect_reddit_data(config)

# Process with sentiment analysis
for post in results['posts']:
    sentiment = analyze_sentiment(post.content)
    # Store sentiment results
```

### Streamlit Dashboard
```python
import streamlit as st
from reddit_api import RedditDataStorage

storage = RedditDataStorage()
posts = storage.query_posts(limit=100)

st.dataframe(posts)
st.line_chart(posts.set_index('timestamp')['upvotes'])
```

## 🐛 Troubleshooting

### Common Issues

1. **401 Authentication Error**:
   - Check client_id and client_secret in .env
   - Verify app type is "script" at reddit.com/prefs/apps

2. **invalid_grant Error**:
   - Remove username/password from config  
   - Use read-only mode (client credentials only)

3. **Rate Limiting**:
   - Normal behavior - requests are automatically queued
   - Monitor with `collector.client.get_metrics()`

4. **No Data Collected**:
   - Check target_keywords filters
   - Verify subreddit names are correct
   - Test with popular subreddits like 'technology'

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built using [PRAW](https://praw.readthedocs.io/) (Python Reddit API Wrapper)
- Originally developed for inflation forecasting via social media sentiment analysis
- Follows Reddit API best practices and terms of service

## 📧 Support

For issues and questions:
1. Check the troubleshooting section above
2. Review Reddit API documentation
3. Open an issue on GitHub with error logs and configuration (anonymized)

---

**Ready to integrate with sentiment analysis pipeline!** 🚀