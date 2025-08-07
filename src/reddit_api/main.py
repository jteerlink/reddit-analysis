"""
Reddit API Data Collection - Main Module

Provides high-level interface for Reddit data collection with configuration
management and orchestration of collection, storage, and analysis.
"""

import logging
import os
from typing import Dict, List, Optional

import praw
from dotenv import load_dotenv

from .collector import RedditDataCollector
from .models import RedditConfig
from .storage import RedditDataStorage

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('reddit_api.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def create_config_from_env() -> RedditConfig:
    """
    Create Reddit configuration from environment variables.
    
    Returns:
        RedditConfig object with values from environment
    """
    # Parse subreddits from environment variable
    target_subreddits = None
    if os.getenv('TARGET_SUBREDDITS'):
        target_subreddits = [sub.strip() for sub in os.getenv('TARGET_SUBREDDITS').split(',')]
    
    # Parse keywords from environment variable
    target_keywords = None
    if os.getenv('TARGET_KEYWORDS'):
        target_keywords = [kw.strip() for kw in os.getenv('TARGET_KEYWORDS').split(',')]
    
    return RedditConfig(
        client_id=os.getenv('REDDIT_CLIENT_ID', 'your_client_id'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET', 'your_client_secret'),
        user_agent=os.getenv('REDDIT_USER_AGENT', 'SentimentAnalyzer:v1.0 (by /u/your_username)'),
        username=os.getenv('REDDIT_USERNAME'),
        password=os.getenv('REDDIT_PASSWORD'),
        
        # Target configuration from environment
        target_subreddits=target_subreddits,
        target_keywords=target_keywords,
        
        # Rate limiting configuration from environment
        max_requests_per_window=int(os.getenv('MAX_REQUESTS_PER_WINDOW', '600')),
        base_delay=float(os.getenv('BASE_DELAY', '1.0')),
        max_delay=float(os.getenv('MAX_DELAY', '60.0')),
        max_retries=int(os.getenv('MAX_RETRIES', '5')),
        circuit_breaker_threshold=int(os.getenv('CIRCUIT_BREAKER_THRESHOLD', '5'))
    )


def test_reddit_connection(config: RedditConfig) -> bool:
    """
    Test Reddit API connection with detailed debugging.
    
    Args:
        config: Reddit configuration to test
        
    Returns:
        True if connection successful, False otherwise
    """
    print("🔍 Testing Reddit API authentication...")
    
    # Check credentials first
    print("\\n📋 Credential Check:")
    print(f"  Client ID: {'✅ Present' if config.client_id and config.client_id != 'your_client_id' else '❌ Missing/Default'}")
    print(f"  Client Secret: {'✅ Present' if config.client_secret and config.client_secret != 'your_client_secret' else '❌ Missing/Default'}")
    print(f"  User Agent: {'✅ Present' if config.user_agent and 'your_username' not in config.user_agent else '⚠️ Default (should be customized)'}")
    
    if config.client_id == 'your_client_id' or config.client_secret == 'your_client_secret':
        print("\\n❌ CRITICAL: Default credentials detected!")
        print("\\n📝 To get Reddit API credentials:")
        print("1. Go to https://www.reddit.com/prefs/apps")
        print("2. Click 'Create App' or 'Create Another App'")
        print("3. Choose 'script' for personal use")
        print("4. Copy the client ID (under the app name)")
        print("5. Copy the client secret")
        print("6. Add them to your .env file:")
        print("   REDDIT_CLIENT_ID=your_actual_client_id")
        print("   REDDIT_CLIENT_SECRET=your_actual_client_secret")
        return False
    
    try:
        # Test read-only access
        print("\\n🔗 Testing read-only API access...")
        test_reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            user_agent=config.user_agent
        )
        
        # Simple test - get subreddit info
        test_subreddit = test_reddit.subreddit('test')
        subreddit_name = test_subreddit.display_name
        
        print(f"✅ Authentication successful!")
        print(f"   Connected to r/{subreddit_name}")
        
        # Try to get one post to verify read access
        try:
            posts = list(test_subreddit.hot(limit=1))
            if posts:
                print(f"   Sample post: {posts[0].title[:50]}...")
                print("✅ Read access confirmed!")
                return True
            else:
                print("✅ Authentication works (no posts in test subreddit)")
                return True
        except Exception as post_error:
            print(f"⚠️ Auth works but post retrieval failed: {post_error}")
            return True  # Auth still works
            
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        print("\\n💡 Common fixes:")
        print("1. Verify your REDDIT_CLIENT_ID is correct")
        print("2. Verify your REDDIT_CLIENT_SECRET is correct") 
        print("3. Ensure your Reddit app type is 'script' at https://reddit.com/prefs/apps")
        print("4. Make sure your user agent is unique and descriptive")
        print("5. Check if your Reddit account email is verified")
        
        # Additional debugging for specific errors
        if "invalid_grant" in str(e):
            print("\\n🔍 invalid_grant Error Analysis:")
            print("  - This usually occurs with username/password auth issues")
            print("  - For data collection, we use read-only mode (no username/password needed)")
            print("  - Your app type should be 'script', not 'web app'")
        elif "401" in str(e):
            print("\\n🔍 401 Error Analysis:")
            print("  - Invalid client_id or client_secret")
            print("  - App might be deleted or suspended")
            print("  - Check https://reddit.com/prefs/apps for your app status")
        elif "403" in str(e):
            print("\\n🔍 403 Error Analysis:")
            print("  - Account might be suspended")
            print("  - Rate limiting (wait and try again)")
        
        return False


def collect_reddit_data(config: RedditConfig, 
                       posts_per_subreddit: int = 5,
                       comments_per_post: int = 10,
                       db_path: str = 'reddit_data.db') -> Dict:
    """
    Collect Reddit data and store in database.
    
    Args:
        config: Reddit configuration
        posts_per_subreddit: Number of posts to collect per subreddit
        comments_per_post: Number of comments to collect per post
        db_path: Path to SQLite database
        
    Returns:
        Dictionary with collection results and statistics
    """
    logger.info("Starting Reddit data collection...")
    
    # Initialize components with storage reference for pre-filtering
    storage = RedditDataStorage(db_path)
    collector = RedditDataCollector(config, storage)
    
    try:
        # Collect data
        results = collector.collect_all_data(
            posts_per_subreddit=posts_per_subreddit,
            comments_per_post=comments_per_post
        )
        
        # Store data
        posts_stored = storage.store_posts(results['posts'])
        comments_stored = storage.store_comments(results['comments'])
        storage.store_metrics(results['metrics'])
        
        # Update collection metadata for efficiency tracking
        collection_time = datetime.now()
        for subreddit in config.target_subreddits:
            # Count posts/comments collected per subreddit
            subreddit_posts = sum(1 for p in results['posts'] if p.subreddit == subreddit)
            subreddit_comments = sum(1 for c in results['comments'] if c.subreddit == subreddit)
            storage.update_collection_metadata(subreddit, collection_time, subreddit_posts, subreddit_comments)
        
        # Run deduplication cleanup after data collection
        logger.info("Running post-collection database deduplication...")
        dedup_stats = storage.deduplicate_database()
        
        # Get updated summary and efficiency stats after deduplication
        summary = storage.get_data_summary()
        efficiency_stats = storage.get_collection_efficiency_stats(days_back=7)
        
        return {
            'success': True,
            'posts_collected': len(results['posts']),
            'comments_collected': len(results['comments']),
            'posts_stored': posts_stored,
            'comments_stored': comments_stored,
            'collection_time': results['collection_time'],
            'api_metrics': results['metrics'],
            'deduplication_stats': dedup_stats,
            'efficiency_stats': efficiency_stats,
            'database_summary': summary
        }
        
    except Exception as e:
        logger.error(f"Data collection failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'posts_collected': 0,
            'comments_collected': 0
        }


def quick_test(config: RedditConfig, test_subreddit: str = 'test') -> bool:
    """
    Perform a quick test to verify data collection works.
    
    Args:
        config: Reddit configuration
        test_subreddit: Subreddit to test with
        
    Returns:
        True if test successful
    """
    print(f"🧪 Quick test: Collecting 1 post from r/{test_subreddit}...")
    
    try:
        collector = RedditDataCollector(config)
        test_posts = collector.collect_subreddit_posts(test_subreddit, limit=1)
        
        if test_posts:
            print(f"✅ SUCCESS! Retrieved {len(test_posts)} post(s)")
            for post in test_posts:
                print(f"   📰 {post.title[:60]}...")
                print(f"   👆 {post.upvotes} upvotes | 💬 {post.num_comments} comments")
        else:
            print(f"⚠️ No posts found in r/{test_subreddit}, but authentication worked!")
        
        print("\\n🎉 Authentication and data collection are working!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        if "invalid_grant" in str(e):
            print("💡 Still getting invalid_grant - check your configuration")
        else:
            print("💡 Check your Reddit credentials and network connection")
        return False


def main():
    """
    Main function demonstrating Reddit data collection.
    """
    print("🚀 Reddit API Data Collection")
    print("=" * 40)
    
    # Create configuration
    config = create_config_from_env()
    
    print(f"Configuration loaded for subreddits: {config.target_subreddits}")
    print(f"Target keywords: {config.target_keywords}")
    
    # Test authentication
    if not test_reddit_connection(config):
        print("\\n🛑 Authentication failed. Please fix credentials before continuing.")
        return
    
    # Quick test
    if not quick_test(config):
        print("\\n🛑 Quick test failed. Check your configuration.")
        return
    
    # Full data collection
    print("\\n🚀 Starting full data collection...")
    results = collect_reddit_data(
        config=config,
        posts_per_subreddit=3,
        comments_per_post=5,
        db_path='reddit_data.db'
    )
    
    if results['success']:
        print("\\n📈 Collection Results:")
        print(f"  Posts collected: {results['posts_collected']}")
        print(f"  Comments collected: {results['comments_collected']}")
        print(f"  Posts stored: {results['posts_stored']}")
        print(f"  Comments stored: {results['comments_stored']}")
        
        # Display deduplication results
        if 'deduplication_stats' in results:
            dedup = results['deduplication_stats']
            print("\\n🧹 Deduplication Results:")
            print(f"  Posts removed: {dedup['posts_removed_total']}")
            print(f"    - By ID: {dedup['posts_removed_by_id']}")
            print(f"    - By content: {dedup['posts_removed_by_content']}")
            print(f"  Comments removed: {dedup['comments_removed_total']}")
            print(f"    - By ID: {dedup['comments_removed_by_id']}")
            print(f"    - By content: {dedup['comments_removed_by_content']}")
            print(f"    - Orphaned: {dedup['orphaned_comments_removed']}")
        
        # Display efficiency statistics
        if 'efficiency_stats' in results:
            eff = results['efficiency_stats']
            print("\\n⚡ Collection Efficiency (last 7 days):")
            print(f"  Total collections: {eff['total_collections']}")
            print(f"  Average posts per run: {eff['avg_posts_per_run']:.1f}")
            print(f"  Average comments per run: {eff['avg_comments_per_run']:.1f}")
            print(f"  Total posts collected: {eff['total_posts_collected']}")
            print(f"  Total comments collected: {eff['total_comments_collected']}")
        
        print("\\n📊 Database Summary (after cleanup):")
        summary = results['database_summary']
        for key, value in summary.items():
            if 'size' in key:
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")
        
        print("\\n🎉 Data collection completed successfully!")
        print("Ready for sentiment analysis integration.")
        
    else:
        print(f"\\n❌ Collection failed: {results['error']}")


if __name__ == "__main__":
    main()