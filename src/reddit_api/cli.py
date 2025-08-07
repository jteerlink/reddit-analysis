#!/usr/bin/env python3
"""
Reddit Data Collection CLI

Command-line interface for Reddit data collection with various options.
"""

import argparse
import sys
from pathlib import Path

from .main import create_config_from_env, test_reddit_connection, collect_reddit_data, quick_test
from .storage import RedditDataStorage
from .historical import TimeFrame, collect_historical_data


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Reddit API Data Collection Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m reddit_api.cli test                    # Test authentication
  python -m reddit_api.cli collect                 # Collect data from default subreddits
  python -m reddit_api.cli collect --posts 10      # Collect 10 posts per subreddit
  python -m reddit_api.cli historical --days 30    # Collect historical data (30 days back)
  python -m reddit_api.cli export data.json        # Export database to JSON
  python -m reddit_api.cli stats                   # Show database statistics
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test Reddit API authentication')
    test_parser.add_argument('--subreddit', default='test', help='Subreddit to test with')
    
    # Collect command
    collect_parser = subparsers.add_parser('collect', help='Collect Reddit data')
    collect_parser.add_argument('--posts', type=int, default=5, help='Posts per subreddit')
    collect_parser.add_argument('--comments', type=int, default=10, help='Comments per post')
    collect_parser.add_argument('--db', default='reddit_data.db', help='Database path')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export data to JSON')
    export_parser.add_argument('filename', help='Output JSON filename')
    export_parser.add_argument('--db', default='reddit_data.db', help='Database path')
    
    # Historical command
    historical_parser = subparsers.add_parser('historical', help='Collect historical Reddit data')
    historical_parser.add_argument('--days', type=int, help='Days back from now to collect')
    historical_parser.add_argument('--start-date', help='Start date (YYYY-MM-DD format)')
    historical_parser.add_argument('--end-date', help='End date (YYYY-MM-DD format)')
    historical_parser.add_argument('--posts', type=int, default=50, help='Posts per subreddit per chunk')
    historical_parser.add_argument('--comments', type=int, default=5, help='Comments per post')
    historical_parser.add_argument('--chunk-days', type=int, default=7, help='Days per processing chunk')
    historical_parser.add_argument('--db', default='historical_reddit_data.db', help='Database path')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show database statistics')
    stats_parser.add_argument('--db', default='reddit_data.db', help='Database path')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Create configuration
    config = create_config_from_env()
    
    if args.command == 'test':
        print("🧪 Testing Reddit API connection...")
        if test_reddit_connection(config):
            if quick_test(config, test_subreddit=args.subreddit):
                print("\\n✅ All tests passed!")
                sys.exit(0)
            else:
                print("\\n❌ Quick test failed!")
                sys.exit(1)
        else:
            print("\\n❌ Authentication test failed!")
            sys.exit(1)
    
    elif args.command == 'collect':
        print(f"🚀 Collecting Reddit data...")
        print(f"   Posts per subreddit: {args.posts}")
        print(f"   Comments per post: {args.comments}")
        print(f"   Database: {args.db}")
        
        results = collect_reddit_data(
            config=config,
            posts_per_subreddit=args.posts,
            comments_per_post=args.comments,
            db_path=args.db
        )
        
        if results['success']:
            print("\\n📈 Collection completed successfully!")
            print(f"   Posts collected: {results['posts_collected']}")
            print(f"   Comments collected: {results['comments_collected']}")
            print(f"   Database: {args.db}")
        else:
            print(f"\\n❌ Collection failed: {results['error']}")
            sys.exit(1)
    
    elif args.command == 'historical':
        print("🕰️  Starting historical Reddit data collection...")
        
        # Parse time frame
        try:
            if args.days:
                time_frame = TimeFrame.from_relative(args.days)
            elif args.start_date and args.end_date:
                time_frame = TimeFrame.from_strings(args.start_date, args.end_date)
            else:
                # Default to last 7 days
                time_frame = TimeFrame.from_relative(7)
                print("⚠️  No time frame specified, defaulting to last 7 days")
            
            print(f"Time frame: {time_frame.start_date.date()} to {time_frame.end_date.date()} ({time_frame.duration_days()} days)")
            print(f"Chunk size: {args.chunk_days} days")
            print(f"Posts per subreddit: {args.posts}")
            print(f"Comments per post: {args.comments}")
            print(f"Database: {args.db}")
            
            # Estimate scope
            chunks = time_frame.split_into_chunks(args.chunk_days)
            print(f"Processing in {len(chunks)} chunks")
            
            # Collect historical data
            results = collect_historical_data(
                time_frame=time_frame,
                config=config,
                db_path=args.db,
                posts_per_subreddit=args.posts,
                comments_per_post=args.comments,
                chunk_days=args.chunk_days
            )
            
            if results['success']:
                print("\\n📈 Historical collection completed!")
                print(f"   Posts collected: {results['posts_collected']}")
                print(f"   Comments collected: {results['comments_collected']}")
                print(f"   Chunks processed: {results['chunks_processed']}")
                if results['errors']:
                    print(f"   Errors: {len(results['errors'])}")
                print(f"   Database: {args.db}")
            else:
                print(f"\\n❌ Historical collection failed: {results.get('error', 'Unknown error')}")
                sys.exit(1)
                
        except Exception as e:
            print(f"❌ Historical collection failed: {e}")
            sys.exit(1)
    
    elif args.command == 'export':
        print(f"📁 Exporting data to {args.filename}...")
        try:
            storage = RedditDataStorage(args.db)
            exported_file = storage.export_to_json(args.filename)
            print(f"✅ Data exported to {exported_file}")
        except Exception as e:
            print(f"❌ Export failed: {e}")
            sys.exit(1)
    
    elif args.command == 'stats':
        print(f"📊 Database statistics for {args.db}...")
        try:
            storage = RedditDataStorage(args.db)
            summary = storage.get_data_summary()
            
            print("\\nOverall Statistics:")
            for key, value in summary.items():
                if 'size' in key:
                    print(f"  {key}: {value:.2f}")
                else:
                    print(f"  {key}: {value}")
            
            # Subreddit stats
            subreddit_stats = storage.get_subreddit_stats()
            if not subreddit_stats.empty:
                print("\\nSubreddit Statistics:")
                for _, row in subreddit_stats.iterrows():
                    print(f"  r/{row['subreddit']}: {row['post_count']} posts "
                          f"(avg {row['avg_upvotes']:.1f} upvotes)")
            
        except Exception as e:
            print(f"❌ Stats failed: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()