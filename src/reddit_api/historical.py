"""
Historical Reddit Data Collection

Extends the existing Reddit API collector to support historical data collection
with user-specified time frames, enhanced rate limiting, and progress tracking.
"""

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import List, NotRequired, Optional, Tuple, TypedDict, Union
from dataclasses import dataclass, field

from .collector import RedditDataCollector
from .models import RedditConfig, RedditPost
from .storage import RedditDataStorage

logger = logging.getLogger(__name__)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None and (name := os.environ.get("REDDIT_COLLECTION_TIMEZONE")):
        value = value.replace(tzinfo=ZoneInfo(name))
    return value.astimezone(timezone.utc)


@dataclass
class TimeFrame:
    """Represents a time frame for historical data collection."""
    start_date: datetime
    end_date: datetime
    
    def __post_init__(self) -> None:
        """Validate time frame."""
        self.start_date = _utc(self.start_date)
        self.end_date = _utc(self.end_date)
        if self.start_date >= self.end_date:
            raise ValueError("Start date must be before end date")
        
        if self.end_date > datetime.now(timezone.utc):
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
            end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days_back)
        return cls(start_date, end_date)
    
    def duration_days(self) -> int:
        """Get duration in days."""
        return (self.end_date - self.start_date).days
    
    def split_into_chunks(self, chunk_days: int = 7) -> List['TimeFrame']:
        """Split time frame into smaller chunks for processing."""
        if chunk_days <= 0:
            raise ValueError("chunk_days must be positive")
        chunks = []
        current_start = self.start_date
        
        while current_start < self.end_date:
            current_end = min(current_start + timedelta(days=chunk_days), self.end_date)
            chunks.append(TimeFrame(current_start, current_end))
            current_start = current_end
        
        return chunks


class HistoricalChunkResult(TypedDict):
    posts_collected: int
    comments_collected: int
    errors: list[str]
    uncovered_intervals: list[dict[str, str]]
    reached: int


class HistoricalCollectionResult(TypedDict):
    success: bool
    status: str
    time_frame: TimeFrame
    chunks_processed: int
    posts_collected: int
    comments_collected: int
    errors: list[str]
    uncovered_intervals: list[dict[str, str]]
    start_time: datetime
    end_time: datetime | None
    error: NotRequired[str]


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
    
    def update_progress(self, chunk_complete: bool = False, posts: int = 0, comments: int = 0, errors: int = 0) -> None:
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
        self.collector = RedditDataCollector(config, storage)
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
    ) -> HistoricalCollectionResult:
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
        self.progress = HistoricalCollectionProgress(total_chunks=len(chunks))
        
        logger.info(f"Processing {len(chunks)} time chunks of ~{chunk_days} days each")
        
        results: HistoricalCollectionResult = {
            'success': False,
            'status': 'failed',
            'time_frame': time_frame,
            'chunks_processed': 0,
            'posts_collected': 0,
            'comments_collected': 0,
            'errors': [],
            'uncovered_intervals': [],
            'start_time': datetime.now(),
            'end_time': None
        }
        
        reached = 0
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
                results['uncovered_intervals'].extend(chunk_results['uncovered_intervals'])
                reached += chunk_results['reached']
                
                self.progress.update_progress(
                    chunk_complete=not (chunk_results["errors"] or chunk_results["uncovered_intervals"]),
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
            ended_at = datetime.now()
            results['end_time'] = ended_at
            duration = ended_at - results['start_time']
            logger.info(f"Historical collection completed in {duration.total_seconds():.1f} seconds")
            logger.info(f"Total collected: {results['posts_collected']} posts, {results['comments_collected']} comments")
            
        issues = results["errors"] or results["uncovered_intervals"] or results.get("error")
        status = ("partial" if reached else "failed") if issues else "complete"
        results["status"] = status
        results["success"] = status == "complete"
        if issues:
            results.setdefault("error", str(issues[0] if isinstance(issues, list) else issues))

        return results
    
    def _collect_chunk(
        self,
        chunk: TimeFrame,
        subreddits: List[str],
        keywords: List[str],
        posts_per_subreddit: int,
        comments_per_post: int
    ) -> HistoricalChunkResult:
        """Collect data for a single time chunk."""
        results: HistoricalChunkResult = {
            "posts_collected": 0,
            "comments_collected": 0,
            "errors": [],
            "uncovered_intervals": [],
            "reached": 0,
        }
        for subreddit in subreddits:
            posts: list[RedditPost] = []
            try:
                posts, oldest = self._collect_time_filtered_posts(
                    subreddit, chunk, posts_per_subreddit, keywords
                )
                if oldest is not None and oldest > chunk.start_date:
                    results["uncovered_intervals"].append({
                        "subreddit": subreddit,
                        "start": chunk.start_date.isoformat(),
                        "end": min(oldest, chunk.end_date).isoformat(),
                        "oldest_seen": oldest.isoformat(),
                    })
                else:
                    results["reached"] += 1
                if posts:
                    stored = self.storage.store_posts(posts)
                    results["posts_collected"] += stored
                    results["reached"] += bool(stored)
                    if stored != len(posts):
                        results["errors"].append(f"Stored {stored} of {len(posts)} posts from r/{subreddit}")
            except Exception as exc:
                results["errors"].append(f"Failed to collect from r/{subreddit}: {exc}")
                self._handle_request_error()

            if comments_per_post > 0:
                self._collect_chunk_comments(subreddit, chunk, keywords, posts, comments_per_post, results)
            self._apply_request_delay()
        return results

    def _collect_chunk_comments(
        self, subreddit: str, chunk: TimeFrame, keywords: List[str],
        posts: List[RedditPost], limit: int, results: HistoricalChunkResult,
    ) -> None:
        post_ids = {post.id: None for post in posts[:10]}
        try:
            if len(post_ids) < 10:
                # The wider query includes legacy local timestamps. Filter exact UTC bounds below.
                margin = timedelta(days=1)
                for post_id, title, content, timestamp in self.storage.get_post_candidates(
                    subreddit, chunk.start_date - margin, chunk.end_date + margin
                ):
                    if timestamp is None:
                        continue
                    date = _utc(timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(timestamp))
                    if chunk.start_date <= date < chunk.end_date and self._contains_keywords(f"{title} {content}", keywords):
                        post_ids[post_id] = None
                    if len(post_ids) == 10:
                        break
        except Exception as exc:
            results["errors"].append(f"Failed to read stored posts from r/{subreddit}: {exc}")

        for post_id in post_ids:
            try:
                comments = self.collector.collect_post_comments(post_id, limit=limit, raise_on_error=True)
                if comments:
                    stored = self.storage.store_comments(comments)
                    results["comments_collected"] += stored
                    results["reached"] += bool(stored)
                    if stored != len(comments):
                        results["errors"].append(f"Stored {stored} of {len(comments)} comments for {post_id}")
                self._apply_request_delay()
            except Exception as exc:
                results["errors"].append(f"Failed to collect comments for {post_id}: {exc}")
                self._handle_request_error()

    def _collect_time_filtered_posts(
        self, subreddit: str, time_frame: TimeFrame, limit: int, keywords: List[str]
    ) -> tuple[list[RedditPost], datetime | None]:
        submissions = self.collector.fetch_new_submissions(subreddit, limit * 3)
        oldest = None
        posts: list[RedditPost] = []
        for submission in submissions:
            timestamp = datetime.fromtimestamp(submission.created_utc, timezone.utc)
            oldest = timestamp if oldest is None else min(oldest, timestamp)
            if len(posts) >= limit or not time_frame.start_date <= timestamp < time_frame.end_date:
                continue
            post = self.collector._extract_post_data(submission)
            if post and self._contains_keywords(f"{post.title} {post.content}", keywords):
                posts.append(post)
        return posts, oldest

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
    
    def _apply_request_delay(self) -> None:
        """Apply delay between API requests."""
        time.sleep(self.current_delay)
        
        # Gradually reduce delay on successful requests
        if self.current_delay > self.base_delay:
            self.current_delay = max(self.base_delay, self.current_delay * 0.9)
    
    def _apply_inter_chunk_delay(self) -> None:
        """Apply delay between processing chunks."""
        chunk_delay = max(5.0, self.current_delay * 2)  # At least 5 seconds between chunks
        logger.debug(f"Applying inter-chunk delay: {chunk_delay:.1f}s")
        time.sleep(chunk_delay)
    
    def _handle_request_error(self) -> None:
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
) -> HistoricalCollectionResult:
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