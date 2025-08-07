"""
Reddit API Data Collection Module

A comprehensive Reddit data collection library with rate limiting, 
circuit breaker patterns, and persistent storage.

Features:
- Rate-limited Reddit API access (600 requests/10min)
- Exponential backoff and circuit breaker patterns
- Structured data storage with SQLite
- Keyword filtering and metadata extraction
- API usage monitoring and error handling

Usage:
    from reddit_api import RedditDataCollector, RedditConfig, RedditDataStorage
    
    # Create configuration
    config = RedditConfig(
        client_id="your_client_id",
        client_secret="your_client_secret", 
        user_agent="YourApp:v1.0 (by /u/yourusername)"
    )
    
    # Collect data
    collector = RedditDataCollector(config)
    posts = collector.collect_subreddit_posts('technology', limit=10)
    
    # Store data
    storage = RedditDataStorage('reddit_data.db')
    storage.store_posts(posts)
"""

from .client import RateLimitedRedditClient, CircuitBreakerState
from .collector import RedditDataCollector
from .models import (
    RedditConfig, 
    RedditPost, 
    RedditComment, 
    ContentType, 
    APIUsageMetrics
)
from .storage import RedditDataStorage
from .main import (
    create_config_from_env,
    test_reddit_connection,
    collect_reddit_data,
    quick_test
)
from .historical import (
    TimeFrame,
    HistoricalRedditCollector,
    collect_historical_data
)

__version__ = "1.0.0"
__author__ = "Reddit API Data Collector"

__all__ = [
    # Core classes
    "RedditConfig",
    "RedditPost", 
    "RedditComment",
    "ContentType",
    "APIUsageMetrics",
    
    # Client classes
    "RateLimitedRedditClient",
    "CircuitBreakerState",
    "RedditDataCollector",
    "RedditDataStorage",
    
    # Utility functions
    "create_config_from_env",
    "test_reddit_connection", 
    "collect_reddit_data",
    "quick_test",
    
    # Historical collection
    "TimeFrame",
    "HistoricalRedditCollector",
    "collect_historical_data"
]