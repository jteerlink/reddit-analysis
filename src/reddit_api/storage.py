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
from typing import Dict, List

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