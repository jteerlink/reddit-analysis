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

    def __init__(self, config: RedditConfig, storage=None):
        """
        Initialize the data collector.

        Args:
            config: Reddit configuration
            storage: Optional RedditDataStorage instance for pre-filtering
        """
        self.config = config
        self.client = RateLimitedRedditClient(config)
        self.storage = storage
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
                                time_filter: str = 'day', sort: str = 'hot',
                                use_pre_filtering: bool = True) -> List[RedditPost]:
        """
        Collect posts from a specific subreddit with optional pre-filtering.

        Args:
            subreddit_name: Name of the subreddit (without r/)
            limit: Maximum number of posts to collect
            time_filter: Time filter for top posts ('day', 'week', 'month', 'year', 'all')
            sort: Sorting method ('hot', 'new', 'top', 'rising')
            use_pre_filtering: Whether to skip posts that already exist in database

        Returns:
            List of RedditPost objects
        """
        # Get existing post IDs for pre-filtering efficiency
        existing_post_ids = set()
        if use_pre_filtering and self.storage:
            existing_post_ids = self.storage.get_existing_post_ids(subreddit_name, days_back=7)
            logger.info(f"Pre-filtering enabled: {len(existing_post_ids)} existing posts in last 7 days")

        logger.info(f"Collecting {limit} {sort} posts from r/{subreddit_name} (time_filter: {time_filter})")

        def _get_subreddit_posts():
            subreddit = self.client.reddit.subreddit(subreddit_name)
            # Increase limit to account for filtered duplicates
            fetch_limit = limit * 2 if use_pre_filtering and existing_post_ids else limit

            if sort == 'hot':
                return subreddit.hot(limit=fetch_limit)
            elif sort == 'new':
                return subreddit.new(limit=fetch_limit)
            elif sort == 'top':
                return subreddit.top(time_filter=time_filter, limit=fetch_limit)
            elif sort == 'rising':
                return subreddit.rising(limit=fetch_limit)
            else:
                return subreddit.hot(limit=fetch_limit)

        try:
            submissions = self.client.make_request(_get_subreddit_posts)
            posts = []
            skipped_existing = 0
            processed = 0

            for submission in submissions:
                # Pre-filtering: Skip posts that already exist
                if use_pre_filtering and submission.id in existing_post_ids:
                    skipped_existing += 1
                    continue

                post_data = self._extract_post_data(submission)
                if post_data:
                    processed += 1

                    # Filter by keywords if specified
                    if self.config.target_keywords:
                        combined_text = f"{post_data.title} {post_data.content}"
                        if self._contains_keywords(combined_text, self.config.target_keywords):
                            posts.append(post_data)
                            logger.info(f"Collected post: {post_data.title[:50]}...")
                    else:
                        posts.append(post_data)
                        logger.info(f"Collected post: {post_data.title[:50]}...")

                    # Stop when we have enough new posts
                    if len(posts) >= limit:
                        break

            self.collected_posts.extend(posts)

            efficiency_msg = f"Successfully collected {len(posts)} posts from r/{subreddit_name}"
            if use_pre_filtering:
                efficiency_msg += f" (skipped {skipped_existing} existing, processed {processed} new)"
            logger.info(efficiency_msg)

            return posts

        except Exception as e:
            logger.error(f"Failed to collect posts from r/{subreddit_name}: {e}")
            return []

    def collect_post_comments(self, post_id: str, limit: int = 20,
                              use_pre_filtering: bool = True) -> List[RedditComment]:
        """
        Collect comments from a specific post with optional pre-filtering.

        Args:
            post_id: Reddit post ID
            limit: Maximum number of comments to collect
            use_pre_filtering: Whether to skip comments that already exist in database

        Returns:
            List of RedditComment objects
        """
        # Get existing comment IDs for pre-filtering efficiency
        existing_comment_ids = set()
        if use_pre_filtering and self.storage:
            existing_comment_ids = self.storage.get_existing_comment_ids([post_id])
            logger.info(f"Pre-filtering enabled: {len(existing_comment_ids)} existing comments for post {post_id}")

        logger.info(f"Collecting {limit} comments from post {post_id}")

        def _get_post_comments():
            submission = self.client.reddit.submission(id=post_id)
            submission.comments.replace_more(limit=0)  # Remove "more comments" objects
            # Fetch more comments if pre-filtering is enabled
            fetch_limit = limit * 2 if use_pre_filtering and existing_comment_ids else limit
            return submission.comments.list()[:fetch_limit]

        try:
            comments_list = self.client.make_request(_get_post_comments)
            comments = []
            skipped_existing = 0
            processed = 0

            for comment in comments_list:
                # Pre-filtering: Skip comments that already exist
                if use_pre_filtering and comment.id in existing_comment_ids:
                    skipped_existing += 1
                    continue

                comment_data = self._extract_comment_data(comment, post_id)
                if comment_data:
                    processed += 1

                    # Filter by keywords if specified
                    if self.config.target_keywords:
                        if self._contains_keywords(comment_data.content, self.config.target_keywords):
                            comments.append(comment_data)
                    else:
                        comments.append(comment_data)

                    # Stop when we have enough new comments
                    if len(comments) >= limit:
                        break

            self.collected_comments.extend(comments)

            efficiency_msg = f"Successfully collected {len(comments)} comments from post {post_id}"
            if use_pre_filtering:
                efficiency_msg += f" (skipped {skipped_existing} existing, processed {processed} new)"
            logger.info(efficiency_msg)

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

    def collect_all_data_with_batching(self, posts_per_subreddit: int = 5, 
                                      comments_per_post: int = 10,
                                      storage_callback=None,
                                      progress_callback=None) -> Dict:
        """
        Collect data from all target subreddits with per-subreddit storage for fault tolerance.
        
        This method stores data immediately after each subreddit completion, preventing
        data loss in case of process failure or cancellation.

        Args:
            posts_per_subreddit: Number of posts to collect per subreddit
            comments_per_post: Number of comments to collect per post
            storage_callback: Function called after each subreddit completion for immediate storage
            progress_callback: Function called to report progress updates

        Returns:
            Dictionary containing collection state and batch results
        """
        logger.info(f"Starting batched data collection from {len(self.config.target_subreddits)} subreddits")

        collection_state = {
            'completed_subreddits': [],
            'failed_subreddits': [],
            'total_posts': 0,
            'total_comments': 0,
            'batch_results': [],
            'start_time': datetime.now().isoformat(),
            'collection_mode': 'batched'
        }

        # Initialize progress tracking
        total_subreddits = len(self.config.target_subreddits)
        
        for idx, subreddit in enumerate(self.config.target_subreddits):
            try:
                logger.info(f"Processing subreddit {idx + 1}/{total_subreddits}: r/{subreddit}")
                
                # Collect subreddit data as a batch
                batch_result = self._collect_subreddit_batch(
                    subreddit, posts_per_subreddit, comments_per_post
                )
                
                # Store immediately if storage callback provided and we have data
                storage_result = None
                if storage_callback and (batch_result['posts'] or batch_result['comments']):
                    try:
                        storage_result = storage_callback(batch_result)
                        batch_result['storage_result'] = storage_result
                        logger.info(f"✅ Batch stored for r/{subreddit}: "
                                  f"{len(batch_result['posts'])} posts, "
                                  f"{len(batch_result['comments'])} comments")
                    except Exception as storage_error:
                        logger.error(f"❌ Storage failed for r/{subreddit}: {storage_error}")
                        batch_result['storage_error'] = str(storage_error)
                        collection_state['failed_subreddits'].append({
                            'subreddit': subreddit,
                            'error_type': 'storage_error',
                            'error': str(storage_error),
                            'batch_data_available': True
                        })
                        # Continue with next subreddit despite storage failure
                        continue
                
                # Update collection state
                collection_state['completed_subreddits'].append(subreddit)
                collection_state['total_posts'] += len(batch_result['posts'])
                collection_state['total_comments'] += len(batch_result['comments'])
                collection_state['batch_results'].append(batch_result)
                
                # Report progress if callback provided
                if progress_callback:
                    progress_info = {
                        'completed': len(collection_state['completed_subreddits']),
                        'total': total_subreddits,
                        'current_subreddit': subreddit,
                        'posts_in_batch': len(batch_result['posts']),
                        'comments_in_batch': len(batch_result['comments']),
                        'total_posts_so_far': collection_state['total_posts'],
                        'total_comments_so_far': collection_state['total_comments']
                    }
                    progress_callback(progress_info)

                # Small delay between subreddits to respect rate limits
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"❌ Failed to collect from r/{subreddit}: {e}")
                collection_state['failed_subreddits'].append({
                    'subreddit': subreddit,
                    'error_type': 'collection_error',
                    'error': str(e),
                    'batch_data_available': False
                })
                continue

        # Final summary
        collection_state['end_time'] = datetime.now().isoformat()
        collection_state['success_rate'] = (
            len(collection_state['completed_subreddits']) / total_subreddits * 100
            if total_subreddits > 0 else 0
        )

        logger.info(f"Batched collection completed: "
                   f"{len(collection_state['completed_subreddits'])}/{total_subreddits} subreddits successful, "
                   f"{collection_state['total_posts']} posts, "
                   f"{collection_state['total_comments']} comments")

        return collection_state

    def _collect_subreddit_batch(self, subreddit: str, posts_limit: int, 
                               comments_limit: int) -> Dict:
        """
        Collect data from a single subreddit and return as a batch.
        
        This method encapsulates the collection of posts and their comments
        for a single subreddit, making it suitable for immediate storage.

        Args:
            subreddit: Name of the subreddit to collect from
            posts_limit: Maximum number of posts to collect
            comments_limit: Maximum number of comments per post

        Returns:
            Dictionary containing batch data and metadata
        """
        batch_start_time = datetime.now()
        
        try:
            # Collect posts from subreddit
            batch_posts = self.collect_subreddit_posts(subreddit, limit=posts_limit)
            batch_comments = []
            
            # Collect comments for each post if requested
            if comments_limit > 0:
                for post in batch_posts:
                    try:
                        post_comments = self.collect_post_comments(post.id, limit=comments_limit)
                        batch_comments.extend(post_comments)
                        # Small delay between comment collections
                        time.sleep(0.5)
                    except Exception as comment_error:
                        logger.warning(f"Failed to collect comments for post {post.id}: {comment_error}")
                        continue

            batch_end_time = datetime.now()
            processing_time = (batch_end_time - batch_start_time).total_seconds()

            return {
                'subreddit': subreddit,
                'posts': batch_posts,
                'comments': batch_comments,
                'collection_time': batch_end_time.isoformat(),
                'batch_metrics': {
                    'posts_count': len(batch_posts),
                    'comments_count': len(batch_comments),
                    'processing_time_seconds': processing_time,
                    'posts_per_second': len(batch_posts) / processing_time if processing_time > 0 else 0,
                    'success': True
                }
            }

        except Exception as e:
            batch_end_time = datetime.now()
            processing_time = (batch_end_time - batch_start_time).total_seconds()
            
            logger.error(f"Batch collection failed for r/{subreddit}: {e}")
            return {
                'subreddit': subreddit,
                'posts': [],
                'comments': [],
                'collection_time': batch_end_time.isoformat(),
                'batch_metrics': {
                    'posts_count': 0,
                    'comments_count': 0,
                    'processing_time_seconds': processing_time,
                    'success': False,
                    'error': str(e)
                }
            }

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
