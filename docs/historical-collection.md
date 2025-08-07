# Historical Reddit Data Collection

Comprehensive guide for collecting historical Reddit data with proper rate limiting and time frame specification.

## 🎯 Overview

The historical Reddit data collection system extends the existing Reddit API collector to support:

- **Time frame-based collection** with flexible date specifications
- **Enhanced rate limiting** with exponential backoff and circuit breaker patterns
- **Progress tracking** with ETA estimates and resumption capabilities
- **Chunk-based processing** for handling large time ranges efficiently
- **Full integration** with existing collector and storage mechanisms

## 🚀 Quick Start

### Using the CLI

```bash
# Collect data from the last 30 days
uv run python -m reddit_api.cli historical --days 30

# Collect data for a specific date range
uv run python -m reddit_api.cli historical --start-date "2024-01-01" --end-date "2024-01-31"

# Custom parameters
uv run python -m reddit_api.cli historical --days 14 --posts 50 --comments 5 --chunk-days 3
```

### Using the Dedicated Script

```bash
# Comprehensive historical collection with all options
python scripts/collect-historical.py --days-back 30 --posts 100 --comments 10

# Specific date range with custom subreddits
python scripts/collect-historical.py --start-date "2024-06-01" --end-date "2024-06-30" \
    --subreddits technology MachineLearning artificial --posts 75
```

### Using Python API

```python
from reddit_api import collect_historical_data, TimeFrame

# Simple collection for last 14 days
results = collect_historical_data(
    time_frame=14,  # Days back
    posts_per_subreddit=50,
    comments_per_post=5
)

# Advanced collection with specific time frame
time_frame = TimeFrame.from_strings("2024-01-01", "2024-01-31")
results = collect_historical_data(
    time_frame=time_frame,
    subreddits=['technology', 'MachineLearning'],
    keywords=['AI', 'machine learning'],
    posts_per_subreddit=100,
    chunk_days=7
)
```

## 📅 Time Frame Specifications

### Relative Time Frames

```python
from reddit_api import TimeFrame

# Last N days from now
last_30_days = TimeFrame.from_relative(30)
last_week = TimeFrame.from_relative(7)
```

### Absolute Date Ranges

```python
# Using ISO date strings
specific_month = TimeFrame.from_strings("2024-01-01", "2024-01-31")

# With time specifications
with_time = TimeFrame.from_strings(
    "2024-01-01T00:00:00", 
    "2024-01-01T23:59:59"
)
```

### Time Frame Operations

```python
time_frame = TimeFrame.from_relative(30)

# Get duration
duration = time_frame.duration_days()  # 30

# Split into chunks for processing
chunks = time_frame.split_into_chunks(7)  # 7-day chunks
print(f"Processing {len(chunks)} chunks")
```

## ⚙️ Rate Limiting & Performance

### Enhanced Rate Limiting

The historical collector implements multi-layer rate limiting:

- **Base delay**: 2 seconds between requests (more conservative than standard collector)
- **Exponential backoff**: Automatic delay increase on errors (2s → 4s → 8s → up to 5 minutes)
- **Inter-chunk delays**: Additional delays between time chunks (minimum 5 seconds)
- **Circuit breaker integration**: Leverages existing circuit breaker patterns

### API Call Estimation

For planning purposes, approximate API calls:

```
Estimated calls = subreddits × chunks × (1 + posts_per_chunk × 0.1)

Example: 3 subreddits × 4 chunks × (1 + 50 × 0.1) = 3 × 4 × 6 = 72 calls
At 2s per call: ~2.4 minutes minimum
```

### Performance Optimization

- **Chunk size**: Smaller chunks (3-5 days) provide more frequent progress updates
- **Post limits**: Balance between data volume and collection time
- **Keyword filtering**: More specific keywords reduce processing overhead

## 📊 Progress Tracking

### Real-time Progress

The historical collector provides comprehensive progress tracking:

```python
from reddit_api import HistoricalRedditCollector, RedditDataStorage

storage = RedditDataStorage('historical.db')
collector = HistoricalRedditCollector(config, storage)

# Progress is automatically tracked during collection
results = collector.collect_historical_data(time_frame, ...)

# Get progress summary anytime
progress = collector.get_progress_summary()
print(progress)
```

### Progress Information

- **Completion percentage**: Based on chunks processed
- **ETA estimates**: Dynamic time remaining calculations
- **Data collected**: Running totals of posts and comments
- **Error tracking**: Count and details of encountered errors

## 🏗️ Architecture & Integration

### Integration with Existing Components

The historical collector leverages existing infrastructure:

```python
# Uses existing collector for actual data retrieval
collector = RedditDataCollector(config)  # Standard collector
historical = HistoricalRedditCollector(config, storage)  # Historical wrapper

# Uses existing storage mechanisms
storage = RedditDataStorage('db.db')  # Standard storage
# All existing storage methods work with historical data

# Uses existing configuration
config = create_config_from_env()  # Standard config
# All existing configuration options apply
```

### Data Model Compatibility

Historical data uses the same data models as standard collection:

- **RedditPost**: Same structure with proper timestamp filtering
- **RedditComment**: Same structure with post relationship maintained
- **Storage schema**: Identical database schema and indexes

## 💻 Usage Examples

### Example 1: Economic Sentiment Analysis

```python
# Collect inflation-related discussions from the last quarter
time_frame = TimeFrame.from_relative(90)  # 3 months

results = collect_historical_data(
    time_frame=time_frame,
    subreddits=['economics', 'investing', 'personalfinance'],
    keywords=['inflation', 'CPI', 'Fed', 'interest rates'],
    posts_per_subreddit=200,
    comments_per_post=15,
    chunk_days=10  # 10-day chunks for quarterly data
)
```

### Example 2: Technology Trend Analysis

```python
# Analyze AI/ML discussions over specific time period
ai_trends = TimeFrame.from_strings("2024-01-01", "2024-06-30")

results = collect_historical_data(
    time_frame=ai_trends,
    subreddits=['MachineLearning', 'artificial', 'technology'],
    keywords=['AI', 'machine learning', 'LLM', 'ChatGPT'],
    posts_per_subreddit=150,
    comments_per_post=10,
    chunk_days=7  # Weekly analysis
)
```

### Example 3: Custom Collection Workflow

```python
from reddit_api import HistoricalRedditCollector, RedditDataStorage

# Initialize components
config = create_config_from_env()
storage = RedditDataStorage('custom_historical.db')
collector = HistoricalRedditCollector(config, storage)

# Define time frame
time_frame = TimeFrame.from_relative(21)  # 3 weeks

# Start collection with custom parameters
results = collector.collect_historical_data(
    time_frame=time_frame,
    subreddits=['technology', 'programming'],
    keywords=['python', 'AI', 'automation'],
    posts_per_subreddit=75,
    comments_per_post=8,
    chunk_days=5
)

# Analyze results
if results['success']:
    # Export collected data
    export_file = storage.export_to_json('historical_export.json')
    
    # Get analytics
    summary = storage.get_data_summary()
    subreddit_stats = storage.get_subreddit_stats()
    
    print(f"Collected: {results['posts_collected']} posts")
    print(f"Database: {summary['database_size_mb']:.2f} MB")
```

## 🔧 Configuration Options

### Collection Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `posts_per_subreddit` | 100 | Posts to collect per subreddit per chunk |
| `comments_per_post` | 10 | Comments to collect per post |
| `chunk_days` | 7 | Days per processing chunk |
| `subreddits` | config default | Target subreddits (overrides config) |
| `keywords` | config default | Filter keywords (overrides config) |

### Rate Limiting Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_delay` | 2.0s | Base delay between requests |
| `max_delay` | 300s | Maximum delay (5 minutes) |
| `backoff_multiplier` | 2.0 | Exponential backoff factor |
| `inter_chunk_delay` | 5.0s minimum | Delay between chunks |

## 🚨 Important Limitations

### Reddit API Constraints

1. **Historical Search Limitations**: Reddit's search API has limited historical reach
2. **Rate Limits**: 600 requests per 10 minutes (enforced by existing rate limiter)
3. **Content Availability**: Deleted posts/comments won't be retrievable
4. **Search Accuracy**: Reddit's search may not return all historical matches

### Data Collection Notes

1. **Time Filtering**: Posts are filtered by creation timestamp after retrieval
2. **Keyword Matching**: Applied to title and content after data collection
3. **Sort Order**: Uses 'new' sort to maximize time-relevant results
4. **Volume Expectations**: Historical data volume may be lower than expected due to API limitations

## 🎯 Best Practices

### For Large Time Ranges (>30 days)

- Use smaller chunk sizes (3-5 days) for better progress tracking
- Set conservative post limits (50-100 per subreddit)
- Monitor progress regularly and be prepared for long collection times
- Consider running during off-peak hours to avoid rate limit issues

### For Targeted Research

- Use specific keywords to reduce noise and processing time
- Focus on active subreddits with good historical content
- Balance comments_per_post with total volume needs
- Export data regularly to prevent loss on interruption

### For Production Use

- Implement checkpoint/resumption logic for very large collections
- Use dedicated database files for historical vs. real-time data
- Monitor disk space - historical collections can be very large
- Consider implementing data retention policies

## 📁 Output and Storage

### Database Schema

Historical data uses the same database schema as standard collection:

- **posts table**: All post metadata with proper timestamps
- **comments table**: Comment data with post relationships
- **api_metrics table**: API usage tracking and performance metrics

### Export Formats

```python
# Standard JSON export (same as regular collection)
storage.export_to_json('historical_data.json')

# Query specific time ranges
posts_df = storage.query_posts(
    start_date='2024-01-01',
    end_date='2024-01-31'
)

# Get time-series analytics
subreddit_stats = storage.get_subreddit_stats()
```

## 🔍 Troubleshooting

### Common Issues

1. **Slow Collection**: Expected for historical data - use smaller chunks and patience
2. **Low Data Volume**: Reddit's historical search limitations - try broader keywords
3. **Rate Limit Errors**: Automatic handling with exponential backoff
4. **Memory Usage**: Historical collections process data in chunks to minimize memory

### Error Recovery

The historical collector includes automatic error recovery:

- **Request failures**: Exponential backoff with retry
- **Circuit breaker trips**: Automatic recovery after cooling period
- **Network issues**: Graceful handling with progress preservation
- **Interrupted collection**: Manual resumption supported

## 🚀 Future Enhancements

Potential improvements for historical collection:

1. **Checkpoint/Resume**: Automatic resumption from interruption points
2. **Parallel Processing**: Multi-threaded chunk processing
3. **External Data Sources**: Integration with historical Reddit data APIs
4. **Smart Filtering**: AI-powered content relevance scoring
5. **Real-time Integration**: Seamless bridging between historical and live data

---

For more examples and detailed API documentation, see:
- `example_historical_collection.py` - Comprehensive usage examples
- `scripts/collect-historical.py` - Full-featured command-line interface
- Source code in `src/reddit_api/historical.py` - Implementation details