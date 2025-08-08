"""
Example: Reddit Mini-Batch Collection

Demonstrates the new fault-tolerant batch collection functionality
that stores data after each subreddit completion.
"""

import os
import time
from src.reddit_api.main import create_config_from_env, collect_reddit_data, test_reddit_connection


def demonstrate_batch_collection():
    """
    Demonstrate batch collection with fault tolerance and resume capability.
    """
    print("🚀 Reddit Mini-Batch Collection Demo")
    print("=" * 50)
    
    # Create configuration from environment
    config = create_config_from_env()
    
    print(f"📋 Configuration:")
    print(f"   Target subreddits: {config.target_subreddits}")
    print(f"   Target keywords: {config.target_keywords}")
    print()
    
    # Test connection first
    if not test_reddit_connection(config):
        print("❌ Connection test failed. Please check your credentials.")
        return
    
    print("✅ Reddit API connection verified!")
    print()
    
    # Demo 1: Standard batch collection
    print("📦 Demo 1: Standard Batch Collection")
    print("   This stores data after each subreddit completion")
    print()
    
    db_path = 'batch_demo.db'
    
    results = collect_reddit_data(
        config=config,
        posts_per_subreddit=3,
        comments_per_post=2,
        db_path=db_path,
        enable_batching=True,      # Enable mini-batch storage
        enable_resume=False        # No resume for fresh start
    )
    
    if results['success']:
        print("✅ Batch collection completed successfully!")
        print(f"   Collection mode: {results['collection_mode']}")
        print(f"   Completed subreddits: {len(results['completed_subreddits'])}")
        print(f"   Failed subreddits: {len(results['failed_subreddits'])}")
        print(f"   Total posts: {results['total_posts_collected']}")
        print(f"   Total comments: {results['total_comments_collected']}")
        print(f"   Success rate: {results['success_rate']:.1f}%")
        
        # Show batch timing
        if results['batch_results']:
            print("\\n📊 Batch Details:")
            for i, batch in enumerate(results['batch_results'][:3]):  # Show first 3
                metrics = batch['batch_metrics']
                print(f"   Batch {i+1} (r/{batch['subreddit']}): "
                      f"{metrics['posts_count']}P, {metrics['comments_count']}C "
                      f"({metrics['processing_time_seconds']:.2f}s)")
        
        # Show deduplication results
        if 'deduplication_stats' in results:
            dedup = results['deduplication_stats']
            if dedup['posts_removed_total'] > 0 or dedup['comments_removed_total'] > 0:
                print("\\n🧹 Deduplication Results:")
                print(f"   Posts removed: {dedup['posts_removed_total']}")
                print(f"   Comments removed: {dedup['comments_removed_total']}")
        
    else:
        print(f"❌ Collection failed: {results['error']}")
        return
    
    print()
    print("⏳ Waiting 5 seconds before next demo...")
    time.sleep(5)
    
    # Demo 2: Resume capability
    print("🔄 Demo 2: Resume Capability")
    print("   This will detect previously completed subreddits and skip them")
    print()
    
    results_resume = collect_reddit_data(
        config=config,
        posts_per_subreddit=3,
        comments_per_post=2,
        db_path=db_path,
        enable_batching=True,
        enable_resume=True         # Enable resume - skip recently completed
    )
    
    if results_resume['success']:
        print("✅ Resume collection completed!")
        print(f"   Resume was enabled: {results_resume.get('enable_resume_was', False)}")
        
        if len(results_resume['completed_subreddits']) == 0:
            print("   🎯 All subreddits were recently completed - nothing to do!")
        else:
            print(f"   Processed {len(results_resume['completed_subreddits'])} additional subreddits")
    
    # Demo 3: Traditional mode comparison
    print()
    print("🔄 Demo 3: Traditional Mode (for comparison)")
    print("   This uses the original behavior - stores all data at the end")
    print()
    
    traditional_db = 'traditional_demo.db'
    
    results_traditional = collect_reddit_data(
        config=config,
        posts_per_subreddit=2,
        comments_per_post=1,
        db_path=traditional_db,
        enable_batching=False      # Disable batching - use original method
    )
    
    if results_traditional['success']:
        print("✅ Traditional collection completed!")
        print(f"   Collection mode: {results_traditional['collection_mode']}")
        print(f"   Posts collected: {results_traditional['posts_collected']}")
        print(f"   Comments collected: {results_traditional['comments_collected']}")
    
    print()
    print("📈 Summary and Recommendations:")
    print("   ✅ Batched mode: Fault-tolerant, progress preserved on failure")
    print("   ✅ Resume capability: Efficient for interrupted long-running collections")
    print("   ✅ Traditional mode: Available for backward compatibility")
    print()
    print("💡 For production use:")
    print("   - Use enable_batching=True for long-running collections")
    print("   - Use enable_resume=True when restarting interrupted collections")
    print("   - Monitor batch_results for performance insights")


def demonstrate_fault_tolerance():
    """
    Demonstrate fault tolerance by simulating failures.
    """
    print()
    print("🛡️ Fault Tolerance Demo")
    print("=" * 30)
    
    from src.reddit_api.storage import RedditDataStorage
    from src.reddit_api.collector import RedditDataCollector
    
    # Create test configuration with mix of valid/invalid subreddits
    fault_config = create_config_from_env()
    # Add some invalid subreddits to trigger failures
    fault_config.target_subreddits = fault_config.target_subreddits + ['nonexistent_subreddit_12345']
    
    print("📋 Testing with mix of valid and invalid subreddits...")
    print(f"   Subreddits: {fault_config.target_subreddits}")
    
    storage = RedditDataStorage('fault_test.db')
    collector = RedditDataCollector(fault_config, storage)
    
    def storage_callback(batch_result):
        print(f"   💾 Storing r/{batch_result['subreddit']}: "
              f"{len(batch_result['posts'])} posts, {len(batch_result['comments'])} comments")
        return storage.store_batch(batch_result)
    
    def progress_callback(progress_info):
        pct = progress_info['completed'] / progress_info['total'] * 100
        print(f"   📊 Progress: {progress_info['completed']}/{progress_info['total']} "
              f"({pct:.1f}%) - r/{progress_info['current_subreddit']} completed")
    
    try:
        collection_state = collector.collect_all_data_with_batching(
            posts_per_subreddit=2,
            comments_per_post=1,
            storage_callback=storage_callback,
            progress_callback=progress_callback
        )
        
        print("\\n✅ Fault tolerance test completed!")
        print(f"   Successful: {len(collection_state['completed_subreddits'])}")
        print(f"   Failed: {len(collection_state['failed_subreddits'])}")
        
        if collection_state['failed_subreddits']:
            print("   Failed subreddits:")
            for failure in collection_state['failed_subreddits']:
                print(f"     - r/{failure['subreddit']}: {failure['error_type']}")
        
        print("   💡 Note: Successful subreddits were still stored despite failures!")
        
    except Exception as e:
        print(f"❌ Fault tolerance test failed: {e}")


if __name__ == '__main__':
    # Run the demonstrations
    demonstrate_batch_collection()
    
    # Uncomment to also run fault tolerance demo
    # demonstrate_fault_tolerance()
    
    print()
    print("🎉 Mini-batch collection demo completed!")
    print("   Check the generated database files:")
    print("   - batch_demo.db (batched collection results)")
    print("   - traditional_demo.db (traditional collection results)")
    print()
    print("📚 Next steps:")
    print("   - Run your collections with enable_batching=True")
    print("   - Use enable_resume=True for interrupted collections")
    print("   - Monitor batch performance with batch_results")