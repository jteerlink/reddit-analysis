#!/usr/bin/env python3
"""
Historical Reddit Data Collection Script

Collects Reddit data for user-specified time frames with proper rate limiting
and progress tracking.
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reddit_api.historical import (
    TimeFrame, 
    HistoricalRedditCollector, 
    collect_historical_data
)
from reddit_api.main import create_config_from_env, test_reddit_connection
from reddit_api.storage import RedditDataStorage


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def parse_time_frame(args) -> TimeFrame:
    """Parse command line arguments into TimeFrame object."""
    if args.days_back:
        return TimeFrame.from_relative(args.days_back)
    
    elif args.start_date and args.end_date:
        return TimeFrame.from_strings(args.start_date, args.end_date)
    
    else:
        # Default to last 7 days if no time frame specified
        print("⚠️  No time frame specified, defaulting to last 7 days")
        return TimeFrame.from_relative(7)


def validate_arguments(args):
    """Validate command line arguments."""
    errors = []
    
    # Check time frame arguments
    if args.days_back and (args.start_date or args.end_date):
        errors.append("Cannot specify both --days-back and --start-date/--end-date")
    
    if (args.start_date or args.end_date) and not (args.start_date and args.end_date):
        errors.append("Must specify both --start-date and --end-date when using date range")
    
    # Validate limits
    if args.posts_per_subreddit < 1 or args.posts_per_subreddit > 1000:
        errors.append("--posts-per-subreddit must be between 1 and 1000")
    
    if args.comments_per_post < 0 or args.comments_per_post > 100:
        errors.append("--comments-per-post must be between 0 and 100")
    
    if args.chunk_days < 1 or args.chunk_days > 365:
        errors.append("--chunk-days must be between 1 and 365")
    
    if errors:
        for error in errors:
            print(f"❌ Error: {error}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Collect historical Reddit data with rate limiting and progress tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Collect data from last 30 days
  python collect-historical.py --days-back 30
  
  # Collect data for specific date range
  python collect-historical.py --start-date "2024-01-01" --end-date "2024-01-31"
  
  # Collect with custom parameters
  python collect-historical.py --days-back 14 --posts 50 --comments 5 --chunk-days 3
  
  # Collect from specific subreddits
  python collect-historical.py --days-back 7 --subreddits technology MachineLearning
  
  # Filter by keywords
  python collect-historical.py --days-back 7 --keywords "AI" "machine learning" "inflation"
  
Date formats:
  - ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
  - Examples: "2024-01-01", "2024-01-01T10:30:00"
        """
    )
    
    # Time frame arguments
    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument(
        '--days-back', 
        type=int,
        help='Number of days back from now to collect data'
    )
    time_group.add_argument(
        '--start-date',
        help='Start date for data collection (ISO format: YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        help='End date for data collection (ISO format: YYYY-MM-DD)'
    )
    
    # Collection parameters
    parser.add_argument(
        '--subreddits',
        nargs='+',
        help='Subreddits to collect from (overrides config default)'
    )
    parser.add_argument(
        '--keywords',
        nargs='+',
        help='Keywords to filter posts by (overrides config default)'
    )
    parser.add_argument(
        '--posts',
        dest='posts_per_subreddit',
        type=int,
        default=100,
        help='Posts per subreddit per time chunk (default: 100)'
    )
    parser.add_argument(
        '--comments',
        dest='comments_per_post',
        type=int,
        default=10,
        help='Comments per post to collect (default: 10)'
    )
    parser.add_argument(
        '--chunk-days',
        type=int,
        default=7,
        help='Days per processing chunk (default: 7)'
    )
    
    # Output and behavior
    parser.add_argument(
        '--database',
        default='historical_reddit_data.db',
        help='Database file path (default: historical_reddit_data.db)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be collected without actually collecting'
    )
    parser.add_argument(
        '--test-connection',
        action='store_true',
        help='Test Reddit API connection and exit'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    print("🕰️  Historical Reddit Data Collection")
    print("=" * 50)
    
    try:
        # Validate arguments
        validate_arguments(args)
        
        # Create configuration
        print("📋 Loading configuration...")
        config = create_config_from_env()
        print(f"Default subreddits: {config.target_subreddits}")
        print(f"Default keywords: {config.target_keywords}")
        
        # Test connection if requested
        if args.test_connection:
            print("\n🔍 Testing Reddit API connection...")
            if test_reddit_connection(config):
                print("✅ Connection successful!")
                sys.exit(0)
            else:
                print("❌ Connection failed!")
                sys.exit(1)
        
        # Parse time frame
        print("\n📅 Parsing time frame...")
        time_frame = parse_time_frame(args)
        duration = time_frame.duration_days()
        
        print(f"Start date: {time_frame.start_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"End date: {time_frame.end_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration: {duration} days")
        
        # Prepare collection parameters
        subreddits = args.subreddits or config.target_subreddits
        keywords = args.keywords or config.target_keywords
        
        print(f"\n📊 Collection parameters:")
        print(f"Subreddits: {subreddits}")
        print(f"Keywords: {keywords}")
        print(f"Posts per subreddit: {args.posts_per_subreddit}")
        print(f"Comments per post: {args.comments_per_post}")
        print(f"Chunk size: {args.chunk_days} days")
        print(f"Database: {args.database}")
        
        # Estimate collection scope
        chunks = time_frame.split_into_chunks(args.chunk_days)
        estimated_requests = len(subreddits) * len(chunks) * (1 + args.posts_per_subreddit * 0.1)  # Rough estimate
        estimated_time_minutes = estimated_requests * 2 / 60  # 2 seconds per request
        
        print(f"\n📈 Estimated scope:")
        print(f"Time chunks: {len(chunks)}")
        print(f"Estimated API requests: ~{estimated_requests:.0f}")
        print(f"Estimated completion time: ~{estimated_time_minutes:.1f} minutes")
        
        if args.dry_run:
            print("\n🧪 Dry run completed - no data collected")
            sys.exit(0)
        
        # Confirm collection
        if estimated_time_minutes > 30:
            response = input(f"\n⚠️  This collection may take ~{estimated_time_minutes:.1f} minutes. Continue? (y/N): ")
            if response.lower() not in ('y', 'yes'):
                print("Collection cancelled")
                sys.exit(0)
        
        # Test Reddit connection
        print("\n🔍 Testing Reddit API connection...")
        if not test_reddit_connection(config):
            print("❌ Authentication failed! Please check your credentials.")
            sys.exit(1)
        print("✅ Connection successful!")
        
        # Initialize storage and collector
        print(f"\n🗄️  Initializing database: {args.database}")
        storage = RedditDataStorage(args.database)
        collector = HistoricalRedditCollector(config, storage)
        
        # Start collection
        print("\n🚀 Starting historical data collection...")
        print(f"Target time frame: {duration} days in {len(chunks)} chunks")
        
        results = collector.collect_historical_data(
            time_frame=time_frame,
            subreddits=subreddits,
            keywords=keywords,
            posts_per_subreddit=args.posts_per_subreddit,
            comments_per_post=args.comments_per_post,
            chunk_days=args.chunk_days
        )
        
        # Report results
        print("\n📊 Collection Results:")
        print("=" * 30)
        
        if results['success']:
            print("✅ Collection completed successfully!")
            duration_minutes = (results['end_time'] - results['start_time']).total_seconds() / 60
            
            print(f"Duration: {duration_minutes:.1f} minutes")
            print(f"Chunks processed: {results['chunks_processed']}")
            print(f"Posts collected: {results['posts_collected']}")
            print(f"Comments collected: {results['comments_collected']}")
            
            # Display deduplication results
            if 'deduplication_stats' in results:
                dedup = results['deduplication_stats']
                print(f"\n🧹 Deduplication Results:")
                print(f"Posts removed: {dedup['posts_removed_total']}")
                print(f"  - By ID: {dedup['posts_removed_by_id']}")
                print(f"  - By content: {dedup['posts_removed_by_content']}")
                print(f"Comments removed: {dedup['comments_removed_total']}")
                print(f"  - By ID: {dedup['comments_removed_by_id']}")
                print(f"  - By content: {dedup['comments_removed_by_content']}")
                print(f"  - Orphaned: {dedup['orphaned_comments_removed']}")
            elif 'deduplication_error' in results:
                print(f"⚠️ Deduplication encountered an error: {results['deduplication_error']}")
            
            if results['errors']:
                print(f"\nErrors encountered: {len(results['errors'])}")
                if args.verbose:
                    for error in results['errors'][:5]:  # Show first 5 errors
                        print(f"  - {error}")
                    if len(results['errors']) > 5:
                        print(f"  ... and {len(results['errors']) - 5} more")
            
            # Show database summary
            summary = storage.get_data_summary()
            print(f"\n📁 Database Summary:")
            print(f"Total posts: {summary['total_posts']}")
            print(f"Total comments: {summary['total_comments']}")
            print(f"Database size: {summary['database_size_mb']:.2f} MB")
            
            print(f"\n💾 Data saved to: {args.database}")
            print("🎉 Historical collection completed successfully!")
            
        else:
            print("❌ Collection failed!")
            print(f"Error: {results.get('error', 'Unknown error')}")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Collection interrupted by user")
        print("Partial data may have been saved to database")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\n❌ Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()