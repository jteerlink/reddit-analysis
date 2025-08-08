"""
Tests for Reddit Mini-Batch Collection System

Comprehensive test coverage for fault-tolerant batch collection functionality.
"""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.reddit_api.collector import RedditDataCollector
from src.reddit_api.storage import RedditDataStorage
from src.reddit_api.models import RedditConfig, RedditPost, RedditComment
from src.reddit_api.exceptions import StorageError
from src.reddit_api.main import collect_reddit_data, _collect_with_batching


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def test_config():
    """Create test configuration."""
    return RedditConfig(
        client_id='test_client',
        client_secret='test_secret',
        user_agent='test_agent',
        target_subreddits=['test1', 'test2', 'test3'],
        target_keywords=['inflation', 'economy']
    )


@pytest.fixture
def mock_reddit_post():
    """Create mock Reddit post."""
    return RedditPost(
        id='test_post_1',
        title='Test Post About Inflation',
        content='This is test content about inflation rates',
        upvotes=100,
        timestamp=datetime.now(),
        subreddit='test1',
        author='test_user',
        author_karma=1000,
        url='https://reddit.com/test',
        num_comments=5
    )


@pytest.fixture
def mock_reddit_comment():
    """Create mock Reddit comment."""
    return RedditComment(
        id='test_comment_1',
        parent_id='test_post_1',
        content='Great insights about the economy',
        upvotes=25,
        timestamp=datetime.now(),
        subreddit='test1',
        author='commenter',
        author_karma=500,
        post_id='test_post_1'
    )


class TestBatchedCollection:
    """Test batched collection functionality."""
    
    def test_successful_batch_collection(self, temp_db, test_config, mock_reddit_post, mock_reddit_comment):
        """Test successful batch collection with immediate storage."""
        storage = RedditDataStorage(temp_db)
        collector = RedditDataCollector(test_config, storage)
        
        # Mock the collector methods to return test data
        with patch.object(collector, 'collect_subreddit_posts') as mock_posts, \
             patch.object(collector, 'collect_post_comments') as mock_comments:
            
            mock_posts.return_value = [mock_reddit_post]
            mock_comments.return_value = [mock_reddit_comment]
            
            # Mock storage callback
            storage_results = []
            def storage_callback(batch_result):
                result = storage.store_batch(batch_result)
                storage_results.append(result)
                return result
            
            # Execute batched collection
            collection_state = collector.collect_all_data_with_batching(
                posts_per_subreddit=1,
                comments_per_post=1,
                storage_callback=storage_callback
            )
            
            # Verify collection state
            assert collection_state['collection_mode'] == 'batched'
            assert len(collection_state['completed_subreddits']) == 3
            assert len(collection_state['failed_subreddits']) == 0
            assert collection_state['total_posts'] == 3  # 1 post per subreddit
            assert collection_state['total_comments'] == 3  # 1 comment per post
            assert collection_state['success_rate'] == 100.0
            
            # Verify storage was called for each subreddit
            assert len(storage_results) == 3
            for result in storage_results:
                assert result['success'] is True
                assert result['posts_stored'] == 1
                assert result['comments_stored'] == 1
            
            # Verify data was actually stored in database
            summary = storage.get_data_summary()
            assert summary['total_posts'] == 3
            assert summary['total_comments'] == 3

    def test_subreddit_failure_isolation(self, temp_db, test_config, mock_reddit_post):
        """Test that one subreddit failure doesn't stop entire collection."""
        storage = RedditDataStorage(temp_db)
        collector = RedditDataCollector(test_config, storage)
        
        # Mock collector to fail on second subreddit
        def mock_collect_posts_side_effect(subreddit, **kwargs):
            if subreddit == 'test2':
                raise Exception("API rate limit exceeded")
            return [mock_reddit_post]
        
        with patch.object(collector, 'collect_subreddit_posts') as mock_posts, \
             patch.object(collector, 'collect_post_comments') as mock_comments:
            
            mock_posts.side_effect = mock_collect_posts_side_effect
            mock_comments.return_value = []
            
            storage_results = []
            def storage_callback(batch_result):
                if batch_result['posts']:  # Only store if there are posts
                    result = storage.store_batch(batch_result)
                    storage_results.append(result)
                    return result
                return {'success': True, 'posts_stored': 0, 'comments_stored': 0}
            
            # Execute batched collection
            collection_state = collector.collect_all_data_with_batching(
                posts_per_subreddit=1,
                comments_per_post=0,
                storage_callback=storage_callback
            )
            
            # Verify collection state shows partial success
            assert len(collection_state['completed_subreddits']) == 2  # test1 and test3
            assert len(collection_state['failed_subreddits']) == 1  # test2
            assert collection_state['failed_subreddits'][0]['subreddit'] == 'test2'
            assert collection_state['failed_subreddits'][0]['error_type'] == 'collection_error'
            assert collection_state['success_rate'] == 66.67  # 2/3 * 100
            
            # Verify successful subreddits were stored
            assert len(storage_results) == 2
            
            # Verify database contains data from successful collections only
            summary = storage.get_data_summary()
            assert summary['total_posts'] == 2


class TestBatchStorage:
    """Test batch storage functionality."""
    
    def test_atomic_batch_storage(self, temp_db, mock_reddit_post, mock_reddit_comment):
        """Test that batch storage is atomic - all or nothing."""
        storage = RedditDataStorage(temp_db)
        
        batch_result = {
            'subreddit': 'test1',
            'posts': [mock_reddit_post],
            'comments': [mock_reddit_comment],
            'collection_time': datetime.now().isoformat(),
            'batch_metrics': {
                'posts_count': 1,
                'comments_count': 1,
                'success': True
            }
        }
        
        # Test successful storage
        result = storage.store_batch(batch_result)
        
        assert result['success'] is True
        assert result['subreddit'] == 'test1'
        assert result['posts_stored'] == 1
        assert result['comments_stored'] == 1
        assert 'transaction_id' in result
        
        # Verify data was stored
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM posts')
            assert cursor.fetchone()[0] == 1
            cursor.execute('SELECT COUNT(*) FROM comments')
            assert cursor.fetchone()[0] == 1
            cursor.execute('SELECT COUNT(*) FROM batch_collections')
            assert cursor.fetchone()[0] == 1

    def test_storage_transaction_rollback(self, temp_db, mock_reddit_post):
        """Test that storage failures rollback cleanly."""
        storage = RedditDataStorage(temp_db)
        
        batch_result = {
            'subreddit': 'test1',
            'posts': [mock_reddit_post],
            'comments': [],
            'collection_time': datetime.now().isoformat()
        }
        
        # Mock database error during storage
        with patch.object(storage, '_store_posts_transaction') as mock_store:
            mock_store.side_effect = sqlite3.Error("Constraint violation")
            
            with pytest.raises(StorageError):
                storage.store_batch(batch_result)
            
            # Verify no partial data was committed
            with sqlite3.connect(temp_db) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM posts')
                assert cursor.fetchone()[0] == 0
                cursor.execute('SELECT COUNT(*) FROM batch_collections')
                assert cursor.fetchone()[0] == 0

    def test_batch_metadata_creation(self, temp_db):
        """Test that batch metadata table is created properly."""
        storage = RedditDataStorage(temp_db)
        
        # Create a batch entry to trigger table creation
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            storage._update_batch_metadata(
                cursor, 'test1', datetime.now(), 5, 10, 2.5
            )
            conn.commit()
            
            # Verify table exists with correct schema
            cursor.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='batch_collections'
            ''')
            assert cursor.fetchone() is not None
            
            # Verify indexes were created
            cursor.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='index' AND tbl_name='batch_collections'
            ''')
            indexes = [row[0] for row in cursor.fetchall()]
            assert 'idx_batch_collections_subreddit' in indexes
            assert 'idx_batch_collections_timestamp' in indexes


class TestResumeCapability:
    """Test resume functionality."""
    
    def test_resume_state_detection(self, temp_db, test_config):
        """Test detection of completed vs pending subreddits."""
        storage = RedditDataStorage(temp_db)
        
        # Simulate some completed collections
        recent_time = datetime.now() - timedelta(hours=2)
        old_time = datetime.now() - timedelta(days=2)
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            
            # Create batch_collections table
            storage._update_batch_metadata(cursor, 'test1', recent_time, 5, 10, 1.0)
            storage._update_batch_metadata(cursor, 'test2', old_time, 3, 5, 1.5)  # Too old
            conn.commit()
        
        # Check resume state
        resume_state = storage.get_collection_resume_state(
            ['test1', 'test2', 'test3'], hours_back=24
        )
        
        assert 'test1' in resume_state['completed_subreddits']
        assert 'test2' in resume_state['pending_subreddits']  # Too old, considered pending
        assert 'test3' in resume_state['pending_subreddits']  # Never collected
        assert resume_state['resume_available'] is True
        assert resume_state['completion_rate'] == 33.33  # 1/3 * 100

    def test_resume_integration_with_collection(self, temp_db, test_config):
        """Test resume capability integrated with main collection."""
        storage = RedditDataStorage(temp_db)
        
        # Pre-populate with completed subreddit
        recent_time = datetime.now() - timedelta(hours=1)
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            storage._update_batch_metadata(cursor, 'test1', recent_time, 5, 10, 1.0)
            conn.commit()
        
        # Mock collection to verify only pending subreddits are processed
        with patch('src.reddit_api.main._collect_with_batching') as mock_collect:
            mock_collect.return_value = {'success': True, 'collection_mode': 'batched'}
            
            # Call with resume enabled
            collect_reddit_data(
                config=test_config,
                enable_batching=True,
                enable_resume=True,
                db_path=temp_db
            )
            
            # Verify the collector was called with filtered subreddits
            args, kwargs = mock_collect.call_args
            collector, storage_obj, config, posts_per, comments_per, enable_resume = args
            
            # The working config should only have pending subreddits
            assert set(collector.config.target_subreddits) == {'test2', 'test3'}


class TestProgressTracking:
    """Test progress tracking and monitoring."""
    
    def test_progress_callback_execution(self, temp_db, test_config, mock_reddit_post):
        """Test that progress callbacks are called correctly."""
        storage = RedditDataStorage(temp_db)
        collector = RedditDataCollector(test_config, storage)
        
        progress_calls = []
        def progress_callback(progress_info):
            progress_calls.append(progress_info)
        
        with patch.object(collector, 'collect_subreddit_posts') as mock_posts, \
             patch.object(collector, 'collect_post_comments') as mock_comments:
            
            mock_posts.return_value = [mock_reddit_post]
            mock_comments.return_value = []
            
            collector.collect_all_data_with_batching(
                posts_per_subreddit=1,
                comments_per_post=0,
                progress_callback=progress_callback
            )
            
            # Verify progress was tracked
            assert len(progress_calls) == 3  # One per subreddit
            
            # Check first progress call
            first_call = progress_calls[0]
            assert first_call['completed'] == 1
            assert first_call['total'] == 3
            assert first_call['current_subreddit'] in test_config.target_subreddits
            assert 'posts_in_batch' in first_call
            assert 'total_posts_so_far' in first_call

    def test_batch_collection_history(self, temp_db):
        """Test batch collection history tracking."""
        storage = RedditDataStorage(temp_db)
        
        # Create some batch history
        times = [
            datetime.now() - timedelta(hours=i) 
            for i in range(5)
        ]
        
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            for i, time in enumerate(times):
                storage._update_batch_metadata(
                    cursor, f'test{i}', time, i+1, (i+1)*2, 1.0 + i*0.1
                )
            conn.commit()
        
        # Get recent history
        history = storage.get_batch_collection_history(limit=3)
        
        assert len(history) == 3
        # Should be in reverse chronological order
        assert history[0]['subreddit'] == 'test0'  # Most recent
        assert history[1]['subreddit'] == 'test1'
        assert history[2]['subreddit'] == 'test2'
        
        # Test filtering by subreddit
        filtered_history = storage.get_batch_collection_history(subreddit='test1', limit=10)
        assert len(filtered_history) == 1
        assert filtered_history[0]['subreddit'] == 'test1'


class TestFaultTolerance:
    """Test fault tolerance scenarios."""
    
    def test_storage_failure_handling(self, temp_db, test_config, mock_reddit_post):
        """Test handling of storage failures during batched collection."""
        storage = RedditDataStorage(temp_db)
        collector = RedditDataCollector(test_config, storage)
        
        # Mock successful data collection but storage failure
        with patch.object(collector, 'collect_subreddit_posts') as mock_posts, \
             patch.object(collector, 'collect_post_comments') as mock_comments:
            
            mock_posts.return_value = [mock_reddit_post]
            mock_comments.return_value = []
            
            def failing_storage_callback(batch_result):
                if batch_result['subreddit'] == 'test2':
                    raise StorageError("Database connection failed")
                return storage.store_batch(batch_result)
            
            collection_state = collector.collect_all_data_with_batching(
                posts_per_subreddit=1,
                comments_per_post=0,
                storage_callback=failing_storage_callback
            )
            
            # Verify partial success with storage failure isolation
            assert len(collection_state['completed_subreddits']) == 2  # test1, test3
            assert len(collection_state['failed_subreddits']) == 1  # test2
            
            storage_failure = collection_state['failed_subreddits'][0]
            assert storage_failure['subreddit'] == 'test2'
            assert storage_failure['error_type'] == 'storage_error'
            assert storage_failure['batch_data_available'] is True

    def test_process_interruption_simulation(self, temp_db, test_config, mock_reddit_post):
        """Test data preservation when process is interrupted mid-collection."""
        storage = RedditDataStorage(temp_db)
        collector = RedditDataCollector(test_config, storage)
        
        stored_batches = []
        def interrupt_after_two_callback(batch_result):
            result = storage.store_batch(batch_result)
            stored_batches.append(result)
            
            if len(stored_batches) >= 2:
                raise KeyboardInterrupt("Process cancelled by user")
            
            return result
        
        with patch.object(collector, 'collect_subreddit_posts') as mock_posts, \
             patch.object(collector, 'collect_post_comments') as mock_comments:
            
            mock_posts.return_value = [mock_reddit_post]
            mock_comments.return_value = []
            
            # Should raise KeyboardInterrupt after 2 successful batches
            with pytest.raises(KeyboardInterrupt):
                collector.collect_all_data_with_batching(
                    posts_per_subreddit=1,
                    comments_per_post=0,
                    storage_callback=interrupt_after_two_callback
                )
            
            # Verify first 2 batches were successfully stored
            assert len(stored_batches) == 2
            
            # Verify database contains the stored data
            summary = storage.get_data_summary()
            assert summary['total_posts'] == 2  # From 2 completed batches


class TestMainIntegration:
    """Test main collection function integration."""
    
    def test_batched_mode_selection(self, temp_db, test_config):
        """Test that batched mode is correctly selected and executed."""
        with patch('src.reddit_api.main._collect_with_batching') as mock_batched:
            mock_batched.return_value = {
                'success': True, 
                'collection_mode': 'batched',
                'total_posts_collected': 5
            }
            
            result = collect_reddit_data(
                config=test_config,
                enable_batching=True,
                db_path=temp_db
            )
            
            assert result['success'] is True
            assert mock_batched.called
            
    def test_traditional_mode_fallback(self, temp_db, test_config):
        """Test that traditional mode still works for backward compatibility."""
        with patch('src.reddit_api.main._collect_traditional_way') as mock_traditional:
            mock_traditional.return_value = {
                'success': True,
                'collection_mode': 'traditional',
                'posts_collected': 5
            }
            
            result = collect_reddit_data(
                config=test_config,
                enable_batching=False,
                db_path=temp_db
            )
            
            assert result['success'] is True
            assert mock_traditional.called

    def test_configuration_validation(self, temp_db, test_config):
        """Test configuration validation and error handling."""
        # Test with invalid database path
        with patch('src.reddit_api.storage.RedditDataStorage') as mock_storage_class:
            mock_storage_class.side_effect = Exception("Cannot create database")
            
            result = collect_reddit_data(
                config=test_config,
                enable_batching=True,
                db_path='/invalid/path/db.sqlite'
            )
            
            assert result['success'] is False
            assert 'error' in result
            assert result['posts_collected'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])