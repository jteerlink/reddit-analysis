#!/usr/bin/env python3
"""
Detailed script to query the historical Reddit data database with comprehensive statistics.

Usage:
    python scripts/query_database_detailed.py
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime


def query_detailed_database_stats(db_path: str = "historical_reddit_data.db") -> dict:
    """
    Query the database for detailed statistics.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        Dictionary containing detailed statistics
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Basic counts
            cursor.execute('SELECT COUNT(*) FROM posts')
            post_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM comments')
            comment_count = cursor.fetchone()[0]
            
            # Subreddit statistics
            cursor.execute('''
                SELECT subreddit, COUNT(*) as post_count, AVG(upvotes) as avg_upvotes
                FROM posts 
                GROUP BY subreddit 
                ORDER BY post_count DESC
            ''')
            subreddit_stats = cursor.fetchall()
            
            # Time-based statistics
            cursor.execute('SELECT MIN(timestamp), MAX(timestamp) FROM posts')
            time_range = cursor.fetchone()
            earliest_post = time_range[0] if time_range[0] else None
            latest_post = time_range[1] if time_range[1] else None
            
            # Recent activity (last 7 days)
            cursor.execute('''
                SELECT COUNT(*) FROM posts 
                WHERE timestamp > datetime('now', '-7 days')
            ''')
            recent_posts = cursor.fetchone()[0]
            
            cursor.execute('''
                SELECT COUNT(*) FROM comments 
                WHERE timestamp > datetime('now', '-7 days')
            ''')
            recent_comments = cursor.fetchone()[0]
            
            # Database size
            db_size_mb = Path(db_path).stat().st_size / (1024 * 1024)
            
            return {
                'post_count': post_count,
                'comment_count': comment_count,
                'subreddit_stats': subreddit_stats,
                'earliest_post': earliest_post,
                'latest_post': latest_post,
                'recent_posts': recent_posts,
                'recent_comments': recent_comments,
                'database_size_mb': round(db_size_mb, 2)
            }
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def format_timestamp(timestamp_str):
    """Format timestamp for display."""
    if not timestamp_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return timestamp_str


def main():
    """Main function to run the detailed database query."""
    print("🔍 Detailed Historical Reddit Data Database Analysis")
    print("=" * 60)
    
    try:
        stats = query_detailed_database_stats()
        
        # Basic statistics
        print(f"\n📊 Basic Statistics:")
        print(f"   Posts: {stats['post_count']:,}")
        print(f"   Comments: {stats['comment_count']:,}")
        print(f"   Total Items: {stats['post_count'] + stats['comment_count']:,}")
        print(f"   Database Size: {stats['database_size_mb']} MB")
        
        # Time range
        print(f"\n📅 Data Time Range:")
        print(f"   Earliest Post: {format_timestamp(stats['earliest_post'])}")
        print(f"   Latest Post: {format_timestamp(stats['latest_post'])}")
        
        # Recent activity
        print(f"\n🕒 Recent Activity (Last 7 Days):")
        print(f"   New Posts: {stats['recent_posts']}")
        print(f"   New Comments: {stats['recent_comments']}")
        
        # Subreddit breakdown
        print(f"\n📈 Subreddit Breakdown:")
        print(f"   {'Subreddit':<20} {'Posts':<8} {'Avg Upvotes':<12}")
        print(f"   {'-' * 20} {'-' * 8} {'-' * 12}")
        
        for subreddit, post_count, avg_upvotes in stats['subreddit_stats']:
            avg_upvotes_str = f"{avg_upvotes:.1f}" if avg_upvotes else "N/A"
            print(f"   {subreddit:<20} {post_count:<8} {avg_upvotes_str:<12}")
        
        # Summary
        print(f"\n💡 Summary:")
        print(f"   • Database contains {stats['post_count']:,} posts and {stats['comment_count']:,} comments")
        print(f"   • Data spans {len(stats['subreddit_stats'])} different subreddits")
        print(f"   • Recent activity shows {stats['recent_posts']} new posts and {stats['recent_comments']} new comments")
        
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        print("Make sure the database file exists in the current directory.")
        sys.exit(1)


if __name__ == "__main__":
    main()
