"""
Reddit API Data Models

Defines data structures for Reddit posts, comments, and configuration.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class ContentType(Enum):
    """Enumeration for content types"""
    POST = "post"
    COMMENT = "comment"


@dataclass
class RedditConfig:
    """Configuration for Reddit API access and data collection"""
    client_id: str
    client_secret: str
    user_agent: str
    username: Optional[str] = None
    password: Optional[str] = None
    
    # Rate limiting configuration
    max_requests_per_window: int = 600
    window_duration_minutes: int = 10
    base_delay: float = 1.0
    max_delay: float = 60.0
    max_retries: int = 5
    circuit_breaker_threshold: int = 5
    
    # Target subreddits and keywords
    target_subreddits: List[str] = None
    target_keywords: List[str] = None
    
    def __post_init__(self):
        """Initialize default values after creation"""
        if self.target_subreddits is None:
            self.target_subreddits = ['technology', 'politics', 'investing', 'MachineLearning']
        if self.target_keywords is None:
            self.target_keywords = ['AI', 'interest rates', 'EVs', 'recession', 'inflation']


@dataclass
class RedditPost:
    """Data model for Reddit posts"""
    id: str
    title: str
    content: str
    upvotes: int
    timestamp: datetime
    subreddit: str
    author: str
    author_karma: int
    url: str
    num_comments: int
    content_type: str = ContentType.POST.value
    
    def to_dict(self) -> Dict:
        """Convert to dictionary with serialized datetime"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class RedditComment:
    """Data model for Reddit comments"""
    id: str
    parent_id: str
    content: str
    upvotes: int
    timestamp: datetime
    subreddit: str
    author: str
    author_karma: int
    post_id: str
    content_type: str = ContentType.COMMENT.value
    
    def to_dict(self) -> Dict:
        """Convert to dictionary with serialized datetime"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class APIUsageMetrics:
    """Metrics for API usage tracking"""
    requests_made: int = 0
    requests_failed: int = 0
    rate_limit_hits: int = 0
    circuit_breaker_trips: int = 0
    last_request_time: Optional[datetime] = None
    window_start: Optional[datetime] = None
    
    def reset_window(self):
        """Reset the tracking window"""
        self.requests_made = 0
        self.window_start = datetime.now()
        
    def to_dict(self) -> Dict:
        """Convert to dictionary with serialized datetimes"""
        return {
            'requests_made': self.requests_made,
            'requests_failed': self.requests_failed,
            'rate_limit_hits': self.rate_limit_hits,
            'circuit_breaker_trips': self.circuit_breaker_trips,
            'last_request_time': self.last_request_time.isoformat() if self.last_request_time else None,
            'window_start': self.window_start.isoformat() if self.window_start else None
        }