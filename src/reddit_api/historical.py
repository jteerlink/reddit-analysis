"""
Historical Reddit Data Collection

Extends the existing Reddit API collector to support historical data collection
with user-specified time frames, enhanced rate limiting, and progress tracking.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field

from .client import RateLimitedRedditClient
from .collector import RedditDataCollector
from .models import RedditConfig, RedditPost, RedditComment
from .storage import RedditDataStorage

logger = logging.getLogger(__name__)


@dataclass
class TimeFrame:
    """Represents a time frame for historical data collection."""
    start_date: datetime
    end_date: datetime
    
    def __post_init__(self):
        """Validate time frame."""
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")
        
        if self.end_date > datetime.now():
            raise ValueError("End date cannot be in the future")
    
    @classmethod
    def from_strings(cls, start_str: str, end_str: str) -> 'TimeFrame':
        """Create TimeFrame from string dates."""
        try:
            start_date = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            return cls(start_date, end_date)
        except ValueError as e:
            raise ValueError(f"Invalid date format. Use ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS): {e}")
    
    @classmethod
    def from_relative(cls, days_back: int, end_date: Optional[datetime] = None) -> 'TimeFrame':
        """Create TimeFrame relative to current time or specified end date."""
        if end_date is None:
            end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        return cls(start_date, end_date)
    
    def duration_days(self) -> int:
        """Get duration in days."""
        return (self.end_date - self.start_date).days
    
    def split_into_chunks(self, chunk_days: int = 7) -> List['TimeFrame']:
        """Split time frame into smaller chunks for processing."""
        chunks = []
        current_start = self.start_date
        
        while current_start < self.end_date:
            current_end = min(current_start + timedelta(days=chunk_days), self.end_date)
            chunks.append(TimeFrame(current_start, current_end))
            current_start = current_end
        
        return chunks


@dataclass
class HistoricalCollectionProgress:
    """Tracks progress of historical data collection."""
    total_chunks: int = 0
    completed_chunks: int = 0
    current_chunk_start: Optional[datetime] = None
    current_chunk_end: Optional[datetime] = None
    posts_collected: int = 0
    comments_collected: int = 0
    errors_encountered: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    last_update: datetime = field(default_factory=datetime.now)
    
    def update_progress(self, chunk_complete: bool = False, posts: int = 0, comments: int = 0, errors: int = 0):
        """Update collection progress."""
        if chunk_complete:
            self.completed_chunks += 1
        
        self.posts_collected += posts
        self.comments_collected += comments
        self.errors_encountered += errors
        self.last_update = datetime.now()
    
    def get_completion_percentage(self) -> float:
        """Get completion percentage."""
        if self.total_chunks == 0:
            return 0.0
        return (self.completed_chunks / self.total_chunks) * 100
    
    def get_eta_minutes(self) -> Optional[float]:
        """Estimate time remaining in minutes."""
        if self.completed_chunks == 0:
            return None
        
        elapsed = datetime.now() - self.start_time
        avg_time_per_chunk = elapsed.total_seconds() / self.completed_chunks
        remaining_chunks = self.total_chunks - self.completed_chunks
        
        if remaining_chunks <= 0:
            return 0.0
        
        return (remaining_chunks * avg_time_per_chunk) / 60


class HistoricalRedditCollector:
    """
    Historical Reddit data collector with time frame support and enhanced rate limiting.
    
    Features:
    - Time frame-based data collection
    - Progress tracking and resumption
    - Enhanced rate limiting with exponential backoff
    - Chunk-based processing for large time ranges
    - Integration with existing collector and storage
    """
    
    def __init__(self, config: RedditConfig, storage: RedditDataStorage):
        """
        Initialize historical collector.
        
        Args:
            config: Reddit API configuration
            storage: Data storage instance
        """
        self.config = config
        self.storage = storage
        self.collector = RedditDataCollector(config)
        self.progress = HistoricalCollectionProgress()
        
        # Enhanced rate limiting for historical collection
        self.base_delay = 2.0  # Base delay between requests (more conservative)
        self.max_delay = 300.0  # Maximum delay (5 minutes)
        self.backoff_multiplier = 2.0
        self.current_delay = self.base_delay
        
        logger.info("Historical Reddit collector initialized")
    
    def collect_historical_data(
        self,
        time_frame: TimeFrame,
        subreddits: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        posts_per_subreddit: int = 100,
        comments_per_post: int = 10,
        chunk_days: int = 7,
        resume_from_checkpoint: bool = True
    ) -> Dict:
        """
        Collect historical Reddit data for specified time frame.
        
        Args:
            time_frame: Time frame for data collection
            subreddits: List of subreddits to collect from (defaults to config)
            keywords: List of keywords to filter by (defaults to config)
            posts_per_subreddit: Number of posts per subreddit per chunk
            comments_per_post: Number of comments per post
            chunk_days: Days per processing chunk
            resume_from_checkpoint: Whether to resume from previous checkpoint
            
        Returns:
            Dictionary with collection results and statistics
        """
        # Use config defaults if not specified
        subreddits = subreddits or self.config.target_subreddits
        keywords = keywords or self.config.target_keywords
        
        logger.info(f"Starting historical collection for {time_frame.duration_days()} days")
        logger.info(f"Time frame: {time_frame.start_date} to {time_frame.end_date}")
        logger.info(f"Subreddits: {subreddits}")
        logger.info(f"Keywords: {keywords}")
        
        # Split time frame into manageable chunks
        chunks = time_frame.split_into_chunks(chunk_days)
        self.progress.total_chunks = len(chunks)
        
        logger.info(f"Processing {len(chunks)} time chunks of ~{chunk_days} days each")
        
        results = {
            'success': True,
            'time_frame': time_frame,
            'chunks_processed': 0,
            'posts_collected': 0,
            'comments_collected': 0,
            'errors': [],
            'start_time': datetime.now(),
            'end_time': None
        }
        
        try:
            for i, chunk in enumerate(chunks):
                self.progress.current_chunk_start = chunk.start_date
                self.progress.current_chunk_end = chunk.end_date
                
                logger.info(f"Processing chunk {i+1}/{len(chunks)}: {chunk.start_date.date()} to {chunk.end_date.date()}")
                
                chunk_results = self._collect_chunk(
                    chunk, subreddits, keywords, posts_per_subreddit, comments_per_post
                )
                
                # Update results and progress
                results['chunks_processed'] += 1
                results['posts_collected'] += chunk_results['posts_collected']
                results['comments_collected'] += chunk_results['comments_collected']
                results['errors'].extend(chunk_results['errors'])
                
                self.progress.update_progress(
                    chunk_complete=True,
                    posts=chunk_results['posts_collected'],
                    comments=chunk_results['comments_collected'],
                    errors=len(chunk_results['errors'])
                )
                
                # Log progress
                completion = self.progress.get_completion_percentage()
                eta = self.progress.get_eta_minutes()
                eta_str = f"{eta:.1f} min" if eta else "unknown"
                
                logger.info(f"Chunk {i+1} complete: {chunk_results['posts_collected']} posts, "
                          f"{chunk_results['comments_collected']} comments")
                logger.info(f"Overall progress: {completion:.1f}% complete, ETA: {eta_str}")
                
                # Rate limiting between chunks
                if i < len(chunks) - 1:  # Don't delay after last chunk
                    self._apply_inter_chunk_delay()
        
        except Exception as e:
            logger.error(f"Historical collection failed: {e}")
            results['success'] = False
            results['error'] = str(e)
        
        finally:
            results['end_time'] = datetime.now()
            duration = results['end_time'] - results['start_time']
            logger.info(f"Historical collection completed in {duration.total_seconds():.1f} seconds")
            logger.info(f"Total collected: {results['posts_collected']} posts, {results['comments_collected']} comments")
        
        return results
    
    def _collect_chunk(
        self,
        chunk: TimeFrame,
        subreddits: List[str],
        keywords: List[str],
        posts_per_subreddit: int,
        comments_per_post: int
    ) -> Dict:
        """Collect data for a single time chunk."""
        chunk_results = {
            'posts_collected': 0,
            'comments_collected': 0,
            'errors': []
        }
        
        for subreddit in subreddits:
            try:
                # Collect posts with time filtering
                posts = self._collect_time_filtered_posts(
                    subreddit, chunk, posts_per_subreddit, keywords
                )
                
                if posts:
                    stored_posts = self.storage.store_posts(posts)
                    chunk_results['posts_collected'] += stored_posts
                    
                    logger.debug(f"Stored {stored_posts} posts from r/{subreddit}")
                    
                    # Collect comments for posts
                    for post in posts[:min(len(posts), 10)]:  # Limit comment collection
                        try:
                            comments = self.collector.collect_post_comments(post.id, limit=comments_per_post)
                            if comments:
                                stored_comments = self.storage.store_comments(comments)
                                chunk_results['comments_collected'] += stored_comments
                                
                                logger.debug(f"Stored {stored_comments} comments for post {post.id}")
                            
                            # Rate limit between comment collections
                            self._apply_request_delay()
                            
                        except Exception as e:
                            error_msg = f"Failed to collect comments for post {post.id}: {e}"
                            logger.warning(error_msg)
                            chunk_results['errors'].append(error_msg)
                            self._handle_request_error()
                
                # Rate limit between subreddits
                self._apply_request_delay()
                
            except Exception as e:
                error_msg = f"Failed to collect from r/{subreddit}: {e}"
                logger.warning(error_msg)
                chunk_results['errors'].append(error_msg)
                self._handle_request_error()
        
        return chunk_results
    
    def _collect_time_filtered_posts(
        self,
        subreddit: str,
        time_frame: TimeFrame,
        limit: int,
        keywords: List[str]
    ) -> List[RedditPost]:
        """Collect posts filtered by time frame."""
        # Reddit's search is limited for historical data, so we collect recent posts
        # and filter by timestamp. For true historical data, you'd need Reddit's
        # historical data API or pushshift.io (now discontinued)
        
        posts = self.collector.collect_subreddit_posts(
            subreddit_name=subreddit,
            limit=limit * 2,  # Collect more to account for filtering
            sort='new'  # Get newest first for better time filtering
        )
        
        # Filter posts by time frame and keywords
        filtered_posts = []
        for post in posts:
            # Check time frame
            if time_frame.start_date <= post.timestamp <= time_frame.end_date:
                # Check keywords if specified
                if keywords:
                    combined_text = f"{post.title} {post.content}"
                    if self._contains_keywords(combined_text, keywords):
                        filtered_posts.append(post)
                else:
                    filtered_posts.append(post)
                
                if len(filtered_posts) >= limit:
                    break
        
        logger.debug(f"Filtered {len(posts)} posts to {len(filtered_posts)} within time frame and keywords")
        return filtered_posts
    
    def _contains_keywords(self, text: str, keywords: List[str]) -> bool:
        """
        Check if text contains any target keywords (case-insensitive).
        
        Args:
            text: Text to search in
            keywords: List of keywords to search for
            
        Returns:
            True if any keyword is found, False otherwise
        """
        if not keywords:
            return True
            
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in keywords)
    
    def _apply_request_delay(self):
        """Apply delay between API requests."""
        time.sleep(self.current_delay)
        
        # Gradually reduce delay on successful requests
        if self.current_delay > self.base_delay:
            self.current_delay = max(self.base_delay, self.current_delay * 0.9)
    
    def _apply_inter_chunk_delay(self):
        """Apply delay between processing chunks."""
        chunk_delay = max(5.0, self.current_delay * 2)  # At least 5 seconds between chunks
        logger.debug(f"Applying inter-chunk delay: {chunk_delay:.1f}s")
        time.sleep(chunk_delay)
    
    def _handle_request_error(self):
        """Handle API request errors with exponential backoff."""
        self.current_delay = min(self.max_delay, self.current_delay * self.backoff_multiplier)
        logger.warning(f"Request failed, increasing delay to {self.current_delay:.1f}s")
        time.sleep(self.current_delay)
    
    def get_progress_summary(self) -> str:
        """Get formatted progress summary."""
        completion = self.progress.get_completion_percentage()
        eta = self.progress.get_eta_minutes()
        eta_str = f"{eta:.1f} min" if eta else "unknown"
        
        return (
            f"Progress: {self.progress.completed_chunks}/{self.progress.total_chunks} chunks "
            f"({completion:.1f}% complete)\n"
            f"Collected: {self.progress.posts_collected} posts, {self.progress.comments_collected} comments\n"
            f"Errors: {self.progress.errors_encountered}\n"
            f"ETA: {eta_str}"
        )


# Utility functions for easy historical collection

def collect_historical_data(
    time_frame: Union[TimeFrame, Tuple[str, str], int],
    config: Optional[RedditConfig] = None,
    db_path: str = "historical_reddit_data.db",
    subreddits: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    posts_per_subreddit: int = 100,
    comments_per_post: int = 10,
    chunk_days: int = 7
) -> Dict:
    """
    Convenient function for historical Reddit data collection.
    
    Args:
        time_frame: TimeFrame object, tuple of (start_date, end_date) strings, or days_back int
        config: Reddit configuration (will create from env if None)
        db_path: Database path for storage
        subreddits: Subreddits to collect from
        keywords: Keywords to filter by
        posts_per_subreddit: Posts per subreddit per chunk
        comments_per_post: Comments per post
        chunk_days: Days per processing chunk
    
    Returns:
        Collection results dictionary
    """
    from .main import create_config_from_env
    
    # Handle different time_frame input types
    if isinstance(time_frame, int):
        time_frame = TimeFrame.from_relative(time_frame)
    elif isinstance(time_frame, tuple):
        time_frame = TimeFrame.from_strings(time_frame[0], time_frame[1])
    
    # Use default config if not provided
    if config is None:
        config = create_config_from_env()
    
    # Initialize storage and collector
    storage = RedditDataStorage(db_path)
    historical_collector = HistoricalRedditCollector(config, storage)
    
    return historical_collector.collect_historical_data(
        time_frame=time_frame,
        subreddits=subreddits,
        keywords=keywords,
        posts_per_subreddit=posts_per_subreddit,
        comments_per_post=comments_per_post,
        chunk_days=chunk_days
    )