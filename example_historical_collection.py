#!/usr/bin/env python3
"""
Historical Reddit Data Collection Examples

Demonstrates various ways to collect historical Reddit data with proper
rate limiting and time frame specification.
"""

import sys
import os

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from reddit_api import (
    TimeFrame,
    HistoricalRedditCollector,
    collect_historical_data,
    create_config_from_env,
    test_reddit_connection,
    RedditDataStorage
)


def example_1_relative_time_frame():
    """Example 1: Collect data from the last 14 days"""
    print("🕰️  Example 1: Last 14 days collection")
    print("=" * 50)
    
    # Create time frame for last 14 days
    time_frame = TimeFrame.from_relative(14)
    print(f"Time frame: {time_frame.start_date.date()} to {time_frame.end_date.date()}")
    
    # Collect data using the convenience function
    results = collect_historical_data(
        time_frame=time_frame,
        db_path='example_14_days.db',
        posts_per_subreddit=25,
        comments_per_post=5,
        chunk_days=3  # Process in 3-day chunks
    )
    
    if results['success']:
        print(f"✅ Collected {results['posts_collected']} posts and {results['comments_collected']} comments")
        print(f"📁 Data saved to: example_14_days.db")
    else:
        print(f"❌ Collection failed: {results.get('error')}")
    
    print()


def example_2_specific_date_range():
    """Example 2: Collect data for a specific date range"""
    print("📅 Example 2: Specific date range (January 2024)")
    print("=" * 50)
    
    # Create time frame for January 2024
    time_frame = TimeFrame.from_strings("2024-01-01", "2024-01-31")
    print(f"Time frame: {time_frame.start_date.date()} to {time_frame.end_date.date()}")
    print(f"Duration: {time_frame.duration_days()} days")
    
    # Collect data with custom parameters
    results = collect_historical_data(
        time_frame=time_frame,
        db_path='example_january_2024.db',
        subreddits=['technology', 'MachineLearning', 'artificial'],
        keywords=['AI', 'artificial intelligence', 'machine learning'],
        posts_per_subreddit=50,
        comments_per_post=8,
        chunk_days=7  # Process in weekly chunks
    )
    
    if results['success']:
        print(f"✅ Collected {results['posts_collected']} posts and {results['comments_collected']} comments")
        print(f"📁 Data saved to: example_january_2024.db")
    else:
        print(f"❌ Collection failed: {results.get('error')}")
    
    print()


def example_3_advanced_collector():
    """Example 3: Advanced usage with HistoricalRedditCollector class"""
    print("🔧 Example 3: Advanced collector with progress tracking")
    print("=" * 50)
    
    # Create configuration and storage
    config = create_config_from_env()
    storage = RedditDataStorage('example_advanced_historical.db')
    
    # Create historical collector
    collector = HistoricalRedditCollector(config, storage)
    
    # Create time frame for last 7 days
    time_frame = TimeFrame.from_relative(7)
    print(f"Time frame: {time_frame.start_date.date()} to {time_frame.end_date.date()}")
    
    # Collect with progress tracking
    results = collector.collect_historical_data(
        time_frame=time_frame,
        subreddits=['technology', 'MachineLearning'],
        keywords=['AI', 'python', 'programming'],
        posts_per_subreddit=30,
        comments_per_post=5,
        chunk_days=2  # Small chunks for frequent progress updates
    )
    
    if results['success']:
        print(f"✅ Collection completed!")
        print(collector.get_progress_summary())
        
        # Show database summary
        summary = storage.get_data_summary()
        print(f"\n📊 Database Summary:")
        print(f"Total posts: {summary['total_posts']}")
        print(f"Total comments: {summary['total_comments']}")
        print(f"Database size: {summary['database_size_mb']:.2f} MB")
    else:
        print(f"❌ Collection failed: {results.get('error')}")
    
    print()


def example_4_time_frame_operations():
    """Example 4: Working with TimeFrame objects"""
    print("⏱️  Example 4: TimeFrame operations")
    print("=" * 50)
    
    # Create different time frames
    last_month = TimeFrame.from_relative(30)
    specific_range = TimeFrame.from_strings("2024-06-01", "2024-06-30")
    
    print(f"Last 30 days: {last_month.start_date.date()} to {last_month.end_date.date()}")
    print(f"Specific range: {specific_range.start_date.date()} to {specific_range.end_date.date()}")
    
    # Split time frames into chunks
    last_month_chunks = last_month.split_into_chunks(7)  # Weekly chunks
    specific_chunks = specific_range.split_into_chunks(5)  # 5-day chunks
    
    print(f"\nLast month split into {len(last_month_chunks)} weekly chunks:")
    for i, chunk in enumerate(last_month_chunks[:3]):  # Show first 3
        print(f"  Chunk {i+1}: {chunk.start_date.date()} to {chunk.end_date.date()}")
    if len(last_month_chunks) > 3:
        print(f"  ... and {len(last_month_chunks) - 3} more chunks")
    
    print(f"\nSpecific range split into {len(specific_chunks)} 5-day chunks:")
    for i, chunk in enumerate(specific_chunks):
        print(f"  Chunk {i+1}: {chunk.start_date.date()} to {chunk.end_date.date()}")
    
    print()


def main():
    """Run all examples"""
    print("🚀 Historical Reddit Data Collection Examples")
    print("=" * 60)
    
    # Test Reddit connection first
    config = create_config_from_env()
    print("🔍 Testing Reddit API connection...")
    if not test_reddit_connection(config):
        print("❌ Authentication failed! Please check your credentials.")
        print("Make sure you have a .env file with valid Reddit API credentials.")
        return
    print("✅ Authentication successful!")
    print()
    
    # Note: These examples are designed to be safe for testing
    # They use small limits and short time frames to avoid hitting API limits
    
    try:
        # Run examples
        example_4_time_frame_operations()  # No API calls
        
        # Uncomment these to run actual data collection
        # WARNING: These will make API requests and may take several minutes
        
        print("⚠️  The following examples will make Reddit API requests.")
        print("They are designed to be safe with small limits, but will take a few minutes.")
        response = input("Continue with data collection examples? (y/N): ")
        
        if response.lower() in ('y', 'yes'):
            example_1_relative_time_frame()
            
            # Space out examples to avoid rate limiting
            print("⏳ Waiting 30 seconds between examples to respect rate limits...")
            import time
            time.sleep(30)
            
            example_2_specific_date_range()
            
            print("⏳ Waiting 30 seconds...")
            time.sleep(30)
            
            example_3_advanced_collector()
        else:
            print("Skipping data collection examples.")
    
    except KeyboardInterrupt:
        print("\n⏹️  Examples interrupted by user")
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
    
    print("\n🎉 Historical collection examples completed!")
    print("\nNext steps:")
    print("- Use the dedicated historical collection script: python scripts/collect-historical.py")
    print("- Use the CLI: python -m reddit_api.cli historical --days 30")
    print("- Integrate historical data with sentiment analysis models")
    print("- Build time-series analysis dashboards")


if __name__ == "__main__":
    main()