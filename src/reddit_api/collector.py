"""
Reddit Data Collector

Handles collection of posts and comments from Reddit with filtering and processing.
"""

import logging
import time
from datetime import datetime
from typing import Dict, List

from .client import RateLimitedRedditClient
from .models import RedditConfig, RedditPost, RedditComment

logger = logging.getLogger(__name__)


class RedditDataCollector:
    """
    Collects Reddit posts and comments with rate limiting and error handling.
    
    Features:
    - Collects posts from multiple subreddits
    - Filters content by keywords
    - Extracts comprehensive metadata
    - Handles API errors gracefully
    """
    
    def __init__(self, config: RedditConfig):
        """
        Initialize the data collector.
        
        Args:
            config: Reddit configuration
        """
        self.config = config
        self.client = RateLimitedRedditClient(config)
        self.collected_posts = []
        self.collected_comments = []
    
    def _extract_post_data(self, submission) -> RedditPost:
        """
        Extract data from a Reddit submission.
        
        Args:
            submission: PRAW submission object
            
        Returns:
            RedditPost object or None if extraction fails
        """
        try:
            return RedditPost(
                id=submission.id,
                title=submission.title,
                content=submission.selftext or "",
                upvotes=submission.score,
                timestamp=datetime.fromtimestamp(submission.created_utc),
                subreddit=submission.subreddit.display_name,
                author=str(submission.author) if submission.author else "[deleted]",
                author_karma=submission.author.comment_karma + submission.author.link_karma if submission.author else 0,
                url=submission.url,
                num_comments=submission.num_comments
            )
        except Exception as e:
            logger.error(f"Error extracting post data: {e}")
            return None

    def _extract_comment_data(self, comment, post_id: str) -> RedditComment:
        """
        Extract data from a Reddit comment.
        
        Args:
            comment: PRAW comment object
            post_id: ID of the parent post
            
        Returns:
            RedditComment object or None if extraction fails
        """
        try:
            if hasattr(comment, 'body') and comment.body != '[deleted]':
                return RedditComment(
                    id=comment.id,
                    parent_id=comment.parent_id,
                    content=comment.body,
                    upvotes=comment.score,
                    timestamp=datetime.fromtimestamp(comment.created_utc),
                    subreddit=comment.subreddit.display_name,
                    author=str(comment.author) if comment.author else "[deleted]",
                    author_karma=comment.author.comment_karma + comment.author.link_karma if comment.author else 0,
                    post_id=post_id
                )
        except Exception as e:
            logger.error(f"Error extracting comment data: {e}")
        return None
    
    def _contains_keywords(self, text: str, keywords: List[str]) -> bool:
        """
        Check if text contains any target keywords.
        
        Args:
            text: Text to search in
            keywords: List of keywords to search for
            
        Returns:
            True if any keyword is found (case-insensitive)
        """
        if not keywords:
            return True
        
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in keywords)

    def collect_subreddit_posts(self, subreddit_name: str, limit: int = 10, 
                               time_filter: str = 'day', sort: str = 'hot') -> List[RedditPost]:
        """
        Collect posts from a specific subreddit.
        
        Args:
            subreddit_name: Name of the subreddit (without r/)
            limit: Maximum number of posts to collect
            time_filter: Time filter for top posts ('day', 'week', 'month', 'year', 'all')
            sort: Sorting method ('hot', 'new', 'top', 'rising')
            
        Returns:
            List of RedditPost objects
        """
        logger.info(f"Collecting {limit} {sort} posts from r/{subreddit_name} (time_filter: {time_filter})")
        
        def _get_subreddit_posts():
            subreddit = self.client.reddit.subreddit(subreddit_name)
            if sort == 'hot':
                return subreddit.hot(limit=limit)
            elif sort == 'new':
                return subreddit.new(limit=limit)
            elif sort == 'top':
                return subreddit.top(time_filter=time_filter, limit=limit)
            elif sort == 'rising':
                return subreddit.rising(limit=limit)
            else:
                return subreddit.hot(limit=limit)
        
        try:
            submissions = self.client.make_request(_get_subreddit_posts)
            posts = []
            
            for submission in submissions:
                post_data = self._extract_post_data(submission)
                if post_data:
                    # Filter by keywords if specified
                    if self.config.target_keywords:
                        combined_text = f"{post_data.title} {post_data.content}"
                        if self._contains_keywords(combined_text, self.config.target_keywords):
                            posts.append(post_data)
                            logger.info(f"Collected post: {post_data.title[:50]}...")
                    else:
                        posts.append(post_data)
                        logger.info(f"Collected post: {post_data.title[:50]}...")
            
            self.collected_posts.extend(posts)
            logger.info(f"Successfully collected {len(posts)} posts from r/{subreddit_name}")
            return posts
            
        except Exception as e:
            logger.error(f"Failed to collect posts from r/{subreddit_name}: {e}")
            return []

    def collect_post_comments(self, post_id: str, limit: int = 20) -> List[RedditComment]:
        """
        Collect comments from a specific post.
        
        Args:
            post_id: Reddit post ID
            limit: Maximum number of comments to collect
            
        Returns:
            List of RedditComment objects
        """
        logger.info(f"Collecting {limit} comments from post {post_id}")
        
        def _get_post_comments():
            submission = self.client.reddit.submission(id=post_id)
            submission.comments.replace_more(limit=0)  # Remove "more comments" objects
            return submission.comments.list()[:limit]
        
        try:
            comments_list = self.client.make_request(_get_post_comments)
            comments = []
            
            for comment in comments_list:
                comment_data = self._extract_comment_data(comment, post_id)
                if comment_data:
                    # Filter by keywords if specified
                    if self.config.target_keywords:
                        if self._contains_keywords(comment_data.content, self.config.target_keywords):
                            comments.append(comment_data)
                    else:
                        comments.append(comment_data)
            
            self.collected_comments.extend(comments)
            logger.info(f"Successfully collected {len(comments)} comments from post {post_id}")
            return comments
            
        except Exception as e:
            logger.error(f"Failed to collect comments from post {post_id}: {e}")
            return []

    def collect_all_data(self, posts_per_subreddit: int = 5, comments_per_post: int = 10) -> Dict:
        """
        Collect data from all target subreddits.
        
        Args:
            posts_per_subreddit: Number of posts to collect per subreddit
            comments_per_post: Number of comments to collect per post
            
        Returns:
            Dictionary containing collected data and metrics
        """
        logger.info(f"Starting data collection from {len(self.config.target_subreddits)} subreddits")
        
        all_posts = []
        all_comments = []
        
        for subreddit in self.config.target_subreddits:
            try:
                # Collect posts
                posts = self.collect_subreddit_posts(subreddit, limit=posts_per_subreddit)
                all_posts.extend(posts)
                
                # Collect comments for each post if requested
                if comments_per_post > 0:
                    for post in posts:
                        comments = self.collect_post_comments(post.id, limit=comments_per_post)
                        all_comments.extend(comments)
                        
                        # Small delay between post comment collections
                        time.sleep(0.5)
                
                # Small delay between subreddits
                time.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error collecting data from r/{subreddit}: {e}")
                continue
        
        results = {
            'posts': all_posts,
            'comments': all_comments,
            'collection_time': datetime.now().isoformat(),
            'metrics': self.client.get_metrics()
        }
        
        logger.info(f"Data collection completed: {len(all_posts)} posts, {len(all_comments)} comments")
        return results

    def get_collector_stats(self) -> Dict:
        """
        Get statistics about the collector's activity.
        
        Returns:
            Dictionary with collector statistics
        """
        return {
            'total_posts_collected': len(self.collected_posts),
            'total_comments_collected': len(self.collected_comments),
            'target_subreddits': self.config.target_subreddits,
            'target_keywords': self.config.target_keywords,
            'client_metrics': self.client.get_metrics()
        }