"""
Reddit API Data Models

Defines data structures for Reddit posts, comments, and configuration.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


DEFAULT_SUBREDDIT_CATEGORIES: tuple[tuple[str, str, str, int], ...] = (
    ("AnthropicAI", "ANTHROPIC", "Anthropic", 10),
    ("ClaudeAI", "ANTHROPIC", "Anthropic", 10),
    ("ChatGPT", "OPENAI", "OpenAI", 20),
    ("OpenAI", "OPENAI", "OpenAI", 20),
    ("Bard", "GOOGLE", "Google AI", 30),
    ("GeminiAI", "GOOGLE", "Google AI", 30),
    ("GoogleGeminiAI", "GOOGLE", "Google AI", 30),
    ("GoogleBard", "GOOGLE", "Google AI", 30),
    ("GoogleAI", "GOOGLE", "Google AI", 30),
    ("DeepMind", "GOOGLE", "Google AI", 30),
    ("nvidia", "AI_INFRA", "AI Infrastructure", 40),
    ("technology", "AI_INFRA", "AI Infrastructure", 40),
    ("huggingface", "AI_INFRA", "AI Infrastructure", 40),
    ("LocalLLaMA", "OPEN_SOURCE", "Open Source", 50),
    ("StableDiffusion", "OPEN_SOURCE", "Open Source", 50),
    ("MachineLearning", "ML_RESEARCH", "ML & Research", 60),
    ("DeepLearning", "ML_RESEARCH", "ML & Research", 60),
    ("datascience", "ML_RESEARCH", "ML & Research", 60),
    ("learnmachinelearning", "ML_RESEARCH", "ML & Research", 60),
    ("artificial", "ML_RESEARCH", "ML & Research", 60),
    ("ArtificialIntelligence", "ML_RESEARCH", "ML & Research", 60),
    ("AITA", "OTHER", "Other", 70),
    ("AGI", "OTHER", "Other", 70),
    ("Singularity", "OTHER", "Other", 70),
    ("AItools", "OTHER", "Other", 70),
    ("aiNews", "OTHER", "Other", 70),
    ("AIStartups", "OTHER", "Other", 70),
    ("AIArt", "OTHER", "Other", 70),
    ("AutoGPT", "OTHER", "Other", 70),
    ("LLMDevs", "OTHER", "Other", 70),
    ("PromptEngineering", "OTHER", "Other", 70),
)

_SUBREDDIT_PARENT_IDS = {
    subreddit.casefold(): parent_id
    for subreddit, parent_id, _display_name, _sort_order in DEFAULT_SUBREDDIT_CATEGORIES
}


def subreddit_parent_id_for(subreddit: Optional[str]) -> str:
    """Return the durable parent group for a subreddit."""
    if not subreddit:
        return "OTHER"
    return _SUBREDDIT_PARENT_IDS.get(subreddit.casefold(), "OTHER")


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
            self.target_subreddits = ['ChatGPT', 'OpenAI', 'ClaudeAI', 'AnthropicAI', 'Bard', 'GeminiAI', 'GoogleGeminiAI', 'GoogleBard', 'GoogleAI', 'AITA', 'LocalLLaMA', 'MachineLearning', 'artificial', 'ArtificialIntelligence', 'DeepLearning', 'AGI', 'Singularity', 'StableDiffusion', 'AItools', 'aiNews', 'huggingface', 'AIStartups', 'DeepMind', 'nvidia', 'AIArt', 'technology', 'LLMDevs', 'PromptEngineering', 'datascience', 'learnmachinelearning']
        if self.target_keywords is None:
            self.target_keywords = ['AI', 'LLM', 'machine learning', 'artificial intelligence', 'ChatGPT', 'Claude', 'GPT', 'neural network']


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
    subreddit_parent_id: Optional[str] = None
    content_type: str = ContentType.POST.value

    def __post_init__(self):
        if not self.subreddit_parent_id:
            self.subreddit_parent_id = subreddit_parent_id_for(self.subreddit)
    
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
    subreddit_parent_id: Optional[str] = None
    content_type: str = ContentType.COMMENT.value

    def __post_init__(self):
        if not self.subreddit_parent_id:
            self.subreddit_parent_id = subreddit_parent_id_for(self.subreddit)
    
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
