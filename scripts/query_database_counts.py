#!/usr/bin/env python3
"""
Script to query the historical Reddit data database and count posts and comments.

Usage:
    python scripts/query_database_counts.py
"""

import sqlite3
import sys
from pathlib import Path


def query_database_counts(db_path: str = "historical_reddit_data.db") -> dict:
    """
    Query the database to count posts and comments.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        Dictionary containing counts and basic statistics
    """
    # Check if database exists
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Count posts
            cursor.execute('SELECT COUNT(*) FROM posts')
            post_count = cursor.fetchone()[0]
            
            # Count comments
            cursor.execute('SELECT COUNT(*) FROM comments')
            comment_count = cursor.fetchone()[0]
            
            # Get some additional statistics
            cursor.execute('SELECT COUNT(DISTINCT subreddit) FROM posts')
            unique_subreddits = cursor.fetchone()[0]
            
            cursor.execute('SELECT MIN(timestamp), MAX(timestamp) FROM posts')
            time_range = cursor.fetchone()
            earliest_post = time_range[0] if time_range[0] else "No posts"
            latest_post = time_range[1] if time_range[1] else "No posts"
            
            # Get database size
            db_size_mb = Path(db_path).stat().st_size / (1024 * 1024)
            
            return {
                'post_count': post_count,
                'comment_count': comment_count,
                'unique_subreddits': unique_subreddits,
                'earliest_post': earliest_post,
                'latest_post': latest_post,
                'database_size_mb': round(db_size_mb, 2)
            }
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def main():
    """Main function to run the database query."""
    print("Querying historical Reddit data database...")
    print("=" * 50)
    
    try:
        stats = query_database_counts()
        
        print(f"📊 Database Statistics:")
        print(f"   Posts: {stats['post_count']:,}")
        print(f"   Comments: {stats['comment_count']:,}")
        print(f"   Unique Subreddits: {stats['unique_subreddits']}")
        print(f"   Database Size: {stats['database_size_mb']} MB")
        print(f"   Date Range: {stats['earliest_post']} to {stats['latest_post']}")
        
        total_items = stats['post_count'] + stats['comment_count']
        print(f"\n📈 Total Items: {total_items:,}")
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("Make sure the database file exists in the current directory.")
        sys.exit(1)


if __name__ == "__main__":
    main()
