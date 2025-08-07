"""
Reddit Data Storage

Handles persistent storage of Reddit data using SQLite with support for
posts, comments, and metadata.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from .models import RedditPost, RedditComment

logger = logging.getLogger(__name__)


class RedditDataStorage:
    """
    Manages persistent storage of Reddit data in SQLite database.

    Features:
    - SQLite database with optimized schema
    - Automatic table creation and indexing
    - Data export functionality
    - Summary statistics
    - Duplicate handling with INSERT OR REPLACE
    """

    def __init__(self, db_path: str = 'reddit_data.db'):
        """
        Initialize storage with database path.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize SQLite database with required tables and indexes"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Posts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content TEXT,
                    upvotes INTEGER,
                    timestamp DATETIME,
                    subreddit TEXT,
                    author TEXT,
                    author_karma INTEGER,
                    url TEXT,
                    num_comments INTEGER,
                    content_type TEXT DEFAULT 'post',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Comments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comments (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    content TEXT NOT NULL,
                    upvotes INTEGER,
                    timestamp DATETIME,
                    subreddit TEXT,
                    author TEXT,
                    author_karma INTEGER,
                    post_id TEXT,
                    content_type TEXT DEFAULT 'comment',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES posts (id)
                )
            ''')

            # API metrics table for tracking usage
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS api_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    requests_made INTEGER,
                    requests_failed INTEGER,
                    rate_limit_hits INTEGER,
                    circuit_breaker_trips INTEGER
                )
            ''')

            # Create indexes for better query performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_timestamp ON comments(timestamp)')

            conn.commit()

        logger.info(f"Database initialized: {self.db_path}")

    def store_posts(self, posts: List[RedditPost]) -> int:
        """
        Store Reddit posts in the database.

        Args:
            posts: List of RedditPost objects to store

        Returns:
            Number of posts successfully stored
        """
        if not posts:
            return 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            stored_count = 0

            for post in posts:
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO posts
                        (id, title, content, upvotes, timestamp, subreddit, author,
                         author_karma, url, num_comments, content_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        post.id, post.title, post.content, post.upvotes,
                        post.timestamp, post.subreddit, post.author,
                        post.author_karma, post.url, post.num_comments, post.content_type
                    ))
                    stored_count += 1
                except Exception as e:
                    logger.error(f"Error storing post {post.id}: {e}")

            conn.commit()

        logger.info(f"Stored {stored_count} posts to database")
        return stored_count

    def store_comments(self, comments: List[RedditComment]) -> int:
        """
        Store Reddit comments in the database.

        Args:
            comments: List of RedditComment objects to store

        Returns:
            Number of comments successfully stored
        """
        if not comments:
            return 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            stored_count = 0

            for comment in comments:
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO comments
                        (id, parent_id, content, upvotes, timestamp, subreddit,
                         author, author_karma, post_id, content_type)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        comment.id, comment.parent_id, comment.content, comment.upvotes,
                        comment.timestamp, comment.subreddit, comment.author,
                        comment.author_karma, comment.post_id, comment.content_type
                    ))
                    stored_count += 1
                except Exception as e:
                    logger.error(f"Error storing comment {comment.id}: {e}")

            conn.commit()

        logger.info(f"Stored {stored_count} comments to database")
        return stored_count

    def store_metrics(self, metrics: Dict):
        """
        Store API usage metrics.

        Args:
            metrics: Dictionary containing API metrics
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO api_metrics
                (requests_made, requests_failed, rate_limit_hits, circuit_breaker_trips)
                VALUES (?, ?, ?, ?)
            ''', (
                metrics.get('requests_made', 0),
                metrics.get('requests_failed', 0),
                metrics.get('rate_limit_hits', 0),
                metrics.get('circuit_breaker_trips', 0)
            ))
            conn.commit()

    def get_data_summary(self) -> Dict:
        """
        Get summary statistics of stored data.

        Returns:
            Dictionary containing data summary
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Posts summary
            cursor.execute('SELECT COUNT(*) FROM posts')
            total_posts = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(DISTINCT subreddit) FROM posts')
            unique_subreddits = cursor.fetchone()[0]

            # Comments summary
            cursor.execute('SELECT COUNT(*) FROM comments')
            total_comments = cursor.fetchone()[0]

            # Recent data
            cursor.execute('SELECT MAX(timestamp) FROM posts')
            latest_post = cursor.fetchone()[0]

            cursor.execute('SELECT MIN(timestamp) FROM posts')
            earliest_post = cursor.fetchone()[0]

            # Database size
            db_size_mb = os.path.getsize(self.db_path) / 1024 / 1024 if os.path.exists(self.db_path) else 0

            return {
                'total_posts': total_posts,
                'total_comments': total_comments,
                'unique_subreddits': unique_subreddits,
                'latest_post': latest_post,
                'earliest_post': earliest_post,
                'database_size_mb': db_size_mb
            }

    def query_posts(self, subreddit: str = None, limit: int = 100,
                    keywords: List[str] = None) -> pd.DataFrame:
        """
        Query posts with optional filters.

        Args:
            subreddit: Filter by specific subreddit
            limit: Maximum number of posts to return
            keywords: Filter by keywords in title or content

        Returns:
            DataFrame containing matching posts
        """
        query = 'SELECT * FROM posts'
        params = []
        conditions = []

        if subreddit:
            conditions.append('subreddit = ?')
            params.append(subreddit)

        if keywords:
            keyword_conditions = []
            for keyword in keywords:
                keyword_conditions.append('(title LIKE ? OR content LIKE ?)')
                params.extend([f'%{keyword}%', f'%{keyword}%'])
            if keyword_conditions:
                conditions.append(f"({' OR '.join(keyword_conditions)})")

        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)

        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)

        return pd.read_sql_query(query, sqlite3.connect(self.db_path), params=params)

    def query_comments(self, post_id: str = None, limit: int = 100) -> pd.DataFrame:
        """
        Query comments with optional filters.

        Args:
            post_id: Filter by specific post ID
            limit: Maximum number of comments to return

        Returns:
            DataFrame containing matching comments
        """
        query = 'SELECT * FROM comments'
        params = []

        if post_id:
            query += ' WHERE post_id = ?'
            params.append(post_id)

        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)

        return pd.read_sql_query(query, sqlite3.connect(self.db_path), params=params)

    def export_to_json(self, filename: str = None) -> str:
        """
        Export all data to JSON file.

        Args:
            filename: Optional filename for export

        Returns:
            Path to exported file
        """
        if not filename:
            filename = f"reddit_data_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        with sqlite3.connect(self.db_path) as conn:
            # Get all data
            posts_df = pd.read_sql_query('SELECT * FROM posts', conn)
            comments_df = pd.read_sql_query('SELECT * FROM comments', conn)
            metrics_df = pd.read_sql_query('SELECT * FROM api_metrics', conn)

            export_data = {
                'posts': posts_df.to_dict('records'),
                'comments': comments_df.to_dict('records'),
                'metrics': metrics_df.to_dict('records'),
                'export_timestamp': datetime.now().isoformat(),
                'summary': self.get_data_summary()
            }

            with open(filename, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)

            logger.info(f"Data exported to {filename}")
            return filename

    def get_subreddit_stats(self) -> pd.DataFrame:
        """
        Get statistics by subreddit.

        Returns:
            DataFrame with subreddit statistics
        """
        query = '''
            SELECT
                subreddit,
                COUNT(*) as post_count,
                AVG(upvotes) as avg_upvotes,
                AVG(num_comments) as avg_comments,
                MAX(timestamp) as latest_post
            FROM posts
            GROUP BY subreddit
            ORDER BY post_count DESC
        '''
        return pd.read_sql_query(query, sqlite3.connect(self.db_path))

    def cleanup_old_data(self, days_to_keep: int = 30) -> int:
        """
        Remove data older than specified days.

        Args:
            days_to_keep: Number of days of data to retain

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Delete old posts
            cursor.execute('DELETE FROM posts WHERE timestamp < ?', (cutoff_date,))
            posts_deleted = cursor.rowcount

            # Delete old comments
            cursor.execute('DELETE FROM comments WHERE timestamp < ?', (cutoff_date,))
            comments_deleted = cursor.rowcount

            conn.commit()

        total_deleted = posts_deleted + comments_deleted
        logger.info(f"Cleaned up {total_deleted} records older than {days_to_keep} days")
        return total_deleted

    def deduplicate_database(self) -> Dict[str, int]:
        """
        Remove duplicate records from the database based on multiple criteria.

        Deduplication strategy:
        - Posts: Remove duplicates by ID (primary), then by title + subreddit + author
        - Comments: Remove duplicates by ID (primary), then by content + post_id + author
        - Keep the record with the latest created_at timestamp for each duplicate group

        Returns:
            Dictionary with counts of duplicates removed
        """
        logger.info("Starting database deduplication...")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Track removal counts
            posts_removed = 0
            comments_removed = 0

            # 1. Remove duplicate posts by ID (keep latest created_at)
            # Note: This handles cases where INSERT OR REPLACE didn't catch duplicates
            cursor.execute('''
                DELETE FROM posts
                WHERE rowid NOT IN (
                    SELECT MAX(rowid)
                    FROM posts
                    GROUP BY id
                )
            ''')
            posts_id_removed = cursor.rowcount
            posts_removed += posts_id_removed

            # 2. Remove posts with same title + subreddit + author (potential content duplicates)
            cursor.execute('''
                DELETE FROM posts
                WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                    FROM posts
                    GROUP BY title, subreddit, author
                )
            ''')
            posts_content_removed = cursor.rowcount
            posts_removed += posts_content_removed

            # 3. Remove duplicate comments by ID (keep latest created_at)
            # Note: This handles cases where INSERT OR REPLACE didn't catch duplicates
            cursor.execute('''
                DELETE FROM comments
                WHERE rowid NOT IN (
                    SELECT MAX(rowid)
                    FROM comments
                    GROUP BY id
                )
            ''')
            comments_id_removed = cursor.rowcount
            comments_removed += comments_id_removed

            # 4. Remove comments with same content + post_id + author (exact duplicates)
            cursor.execute('''
                DELETE FROM comments
                WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                    FROM comments
                    GROUP BY content, post_id, author
                )
            ''')
            comments_content_removed = cursor.rowcount
            comments_removed += comments_content_removed

            # 5. Remove orphaned comments (comments whose posts no longer exist)
            cursor.execute('''
                DELETE FROM comments
                WHERE post_id NOT IN (SELECT id FROM posts)
            ''')
            orphaned_comments = cursor.rowcount
            comments_removed += orphaned_comments

            conn.commit()

            # Log detailed results
            logger.info("Deduplication completed:")
            logger.info(f"  Posts removed by ID: {posts_id_removed}")
            logger.info(f"  Posts removed by content: {posts_content_removed}")
            logger.info(f"  Comments removed by ID: {comments_id_removed}")
            logger.info(f"  Comments removed by content: {comments_content_removed}")
            logger.info(f"  Orphaned comments removed: {orphaned_comments}")
            logger.info(f"  Total posts removed: {posts_removed}")
            logger.info(f"  Total comments removed: {comments_removed}")

            return {
                'posts_removed_total': posts_removed,
                'posts_removed_by_id': posts_id_removed,
                'posts_removed_by_content': posts_content_removed,
                'comments_removed_total': comments_removed,
                'comments_removed_by_id': comments_id_removed,
                'comments_removed_by_content': comments_content_removed,
                'orphaned_comments_removed': orphaned_comments
            }

    def get_duplicate_stats(self) -> Dict[str, int]:
        """
        Get statistics about potential duplicates in the database.

        Returns:
            Dictionary with duplicate counts before cleanup
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Count duplicate posts by ID
            cursor.execute('''
                SELECT COUNT(*) - COUNT(DISTINCT id)
                FROM posts
            ''')
            duplicate_posts_by_id = cursor.fetchone()[0]

            # Count duplicate posts by content
            cursor.execute('''
                SELECT COUNT(*) - COUNT(DISTINCT title || subreddit || author)
                FROM posts
            ''')
            duplicate_posts_by_content = cursor.fetchone()[0]

            # Count duplicate comments by ID
            cursor.execute('''
                SELECT COUNT(*) - COUNT(DISTINCT id)
                FROM comments
            ''')
            duplicate_comments_by_id = cursor.fetchone()[0]

            # Count duplicate comments by content
            cursor.execute('''
                SELECT COUNT(*) - COUNT(DISTINCT content || post_id || author)
                FROM comments
            ''')
            duplicate_comments_by_content = cursor.fetchone()[0]

            # Count orphaned comments
            cursor.execute('''
                SELECT COUNT(*)
                FROM comments
                WHERE post_id NOT IN (SELECT id FROM posts)
            ''')
            orphaned_comments = cursor.fetchone()[0]

            return {
                'duplicate_posts_by_id': duplicate_posts_by_id,
                'duplicate_posts_by_content': duplicate_posts_by_content,
                'duplicate_comments_by_id': duplicate_comments_by_id,
                'duplicate_comments_by_content': duplicate_comments_by_content,
                'orphaned_comments': orphaned_comments
            }
    
    def get_existing_post_ids(self, subreddit: str = None, days_back: int = 7) -> set:
        """
        Get set of existing post IDs for efficient duplicate checking.
        
        Args:
            subreddit: Filter by specific subreddit (None for all)
            days_back: How many days back to check for IDs
            
        Returns:
            Set of post IDs that already exist in database
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            if subreddit:
                cursor.execute('''
                    SELECT id FROM posts 
                    WHERE subreddit = ? AND timestamp > ?
                ''', (subreddit, cutoff_date))
            else:
                cursor.execute('''
                    SELECT id FROM posts 
                    WHERE timestamp > ?
                ''', (cutoff_date,))
            
            return {row[0] for row in cursor.fetchall()}
    
    def get_existing_post_ids_in_timeframe(self, subreddit: str, start_date: datetime, end_date: datetime) -> set:
        """
        Get existing post IDs within a specific timeframe for historical collection.
        
        Args:
            subreddit: Subreddit to check
            start_date: Start of timeframe
            end_date: End of timeframe
            
        Returns:
            Set of post IDs that already exist in the timeframe
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id FROM posts 
                WHERE subreddit = ? AND timestamp BETWEEN ? AND ?
            ''', (subreddit, start_date, end_date))
            
            return {row[0] for row in cursor.fetchall()}
    
    def get_existing_comment_ids(self, post_ids: List[str] = None, days_back: int = 7) -> set:
        """
        Get set of existing comment IDs for efficient duplicate checking.
        
        Args:
            post_ids: Filter by specific post IDs (None for recent comments)
            days_back: How many days back to check for IDs
            
        Returns:
            Set of comment IDs that already exist in database
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if post_ids:
                # Use IN clause for specific posts
                placeholders = ','.join('?' for _ in post_ids)
                cursor.execute(f'''
                    SELECT id FROM comments 
                    WHERE post_id IN ({placeholders})
                ''', post_ids)
            else:
                # Use time-based filtering for recent comments
                cutoff_date = datetime.now() - timedelta(days=days_back)
                cursor.execute('''
                    SELECT id FROM comments 
                    WHERE timestamp > ?
                ''', (cutoff_date,))
            
            return {row[0] for row in cursor.fetchall()}
    
    def get_last_collection_timestamp(self, subreddit: str) -> Optional[datetime]:
        """
        Get the timestamp of the most recent post collected for a subreddit.
        
        Args:
            subreddit: Subreddit to check
            
        Returns:
            Datetime of most recent post, or None if no posts exist
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT MAX(timestamp) FROM posts 
                WHERE subreddit = ?
            ''', (subreddit,))
            
            result = cursor.fetchone()[0]
            return datetime.fromisoformat(result) if result else None
    
    def update_collection_metadata(self, subreddit: str, collection_time: datetime, 
                                 posts_collected: int, comments_collected: int):
        """
        Store metadata about collection runs for efficiency tracking.
        
        Args:
            subreddit: Subreddit that was collected
            collection_time: When the collection occurred
            posts_collected: Number of posts collected
            comments_collected: Number of comments collected
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create metadata table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS collection_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subreddit TEXT NOT NULL,
                    collection_timestamp DATETIME NOT NULL,
                    posts_collected INTEGER DEFAULT 0,
                    comments_collected INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insert collection metadata
            cursor.execute('''
                INSERT INTO collection_metadata 
                (subreddit, collection_timestamp, posts_collected, comments_collected)
                VALUES (?, ?, ?, ?)
            ''', (subreddit, collection_time, posts_collected, comments_collected))
            
            conn.commit()
    
    def get_collection_efficiency_stats(self, subreddit: str = None, days_back: int = 30) -> Dict:
        """
        Get efficiency statistics for recent collections.
        
        Args:
            subreddit: Filter by specific subreddit (None for all)
            days_back: How many days back to analyze
            
        Returns:
            Dictionary with efficiency metrics
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            # Get basic collection stats
            if subreddit:
                cursor.execute('''
                    SELECT 
                        COUNT(*) as collections,
                        SUM(posts_collected) as total_posts,
                        SUM(comments_collected) as total_comments,
                        AVG(posts_collected) as avg_posts_per_run,
                        AVG(comments_collected) as avg_comments_per_run
                    FROM collection_metadata 
                    WHERE subreddit = ? AND collection_timestamp > ?
                ''', (subreddit, cutoff_date))
            else:
                cursor.execute('''
                    SELECT 
                        COUNT(*) as collections,
                        SUM(posts_collected) as total_posts,
                        SUM(comments_collected) as total_comments,
                        AVG(posts_collected) as avg_posts_per_run,
                        AVG(comments_collected) as avg_comments_per_run
                    FROM collection_metadata 
                    WHERE collection_timestamp > ?
                ''', (cutoff_date,))
            
            result = cursor.fetchone()
            
            return {
                'total_collections': result[0] or 0,
                'total_posts_collected': result[1] or 0,
                'total_comments_collected': result[2] or 0,
                'avg_posts_per_run': result[3] or 0,
                'avg_comments_per_run': result[4] or 0,
                'analysis_period_days': days_back
            }
