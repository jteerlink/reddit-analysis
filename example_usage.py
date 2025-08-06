#!/usr/bin/env python3
"""
Reddit API Data Collection - Example Usage

Demonstrates how to use the Reddit API module for data collection.
"""

import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from reddit_api import (
    RedditConfig, 
    RedditDataCollector, 
    RedditDataStorage,
    create_config_from_env,
    test_reddit_connection,
    collect_reddit_data
)


def main():
    """Example usage of Reddit API data collection"""
    print("🚀 Reddit API Data Collection - Example Usage")
    print("=" * 50)
    
    # Method 1: Create configuration from environment variables
    print("📋 Loading configuration from environment...")
    config = create_config_from_env()
    print(f"Target subreddits: {config.target_subreddits}")
    print(f"Target keywords: {config.target_keywords}")
    
    # Method 2: Create configuration manually
    # config = RedditConfig(
    #     client_id="your_client_id",
    #     client_secret="your_client_secret",
    #     user_agent="YourApp:v1.0 (by /u/yourusername)",
    #     target_subreddits=['technology', 'MachineLearning'],
    #     target_keywords=['AI', 'machine learning']
    # )
    
    # Test authentication
    print("🔍 Testing Reddit API authentication...")
    if not test_reddit_connection(config):
        print("❌ Authentication failed! Please check your credentials.")
        return
    
    # Example 1: Simple data collection
    print("📊 Example 1: Simple Data Collection")
    print("-" * 40)
    
    results = collect_reddit_data(
        config=config,
        posts_per_subreddit=3,
        comments_per_post=5,
        db_path='example_reddit_data.db'
    )
    
    if results['success']:
        print(f"✅ Collected {results['posts_collected']} posts and {results['comments_collected']} comments")
    else:
        print(f"❌ Collection failed: {results['error']}")
        return
    
    # Example 2: Advanced usage with individual components
    print("🔧 Example 2: Advanced Usage")
    print("-" * 40)
    
    # Initialize components separately
    collector = RedditDataCollector(config)
    storage = RedditDataStorage('example_advanced.db')
    
    # Collect from specific subreddit
    posts = collector.collect_subreddit_posts('technology', limit=5, sort='hot')
    print(f"Collected {len(posts)} posts from r/technology")
    
    # Collect comments for first post
    if posts:
        comments = collector.collect_post_comments(posts[0].id, limit=10)
        print(f"Collected {len(comments)} comments from top post")
        
        # Store data
        stored_posts = storage.store_posts(posts)
        stored_comments = storage.store_comments(comments)
        print(f"Stored {stored_posts} posts and {stored_comments} comments")
    
    # Example 3: Data analysis and export
    print("📈 Example 3: Data Analysis")
    print("-" * 40)
    
    # Get summary statistics
    summary = storage.get_data_summary()
    print("Database Summary:")
    for key, value in summary.items():
        if 'size' in key:
            print(f"  {key}: {value:.2f} MB")
        else:
            print(f"  {key}: {value}")
    
    # Query data with filters
    tech_posts = storage.query_posts(subreddit='technology', limit=10)
    if not tech_posts.empty:
        print(f"Found {len(tech_posts)} technology posts")
        top_post = tech_posts.iloc[0]
        print(f"Top post: {top_post['title'][:60]}...")
    
    # Export data
    export_file = storage.export_to_json('reddit_export.json')
    print(f"📁 Data exported to {export_file}")
    
    # Get subreddit statistics
    subreddit_stats = storage.get_subreddit_stats()
    if not subreddit_stats.empty:
        print("📊 Subreddit Statistics:")
        for _, row in subreddit_stats.iterrows():
            print(f"  r/{row['subreddit']}: {row['post_count']} posts "
                  f"(avg {row['avg_upvotes']:.1f} upvotes)")
    
    print("🎉 Example completed successfully!")
    print("Next steps:")
    print("- Integrate with sentiment analysis models")
    print("- Add real-time streaming capabilities")
    print("- Scale to production with PostgreSQL")
    print("- Build Streamlit dashboard for visualization")


if __name__ == "__main__":
    main()