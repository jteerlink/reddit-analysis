# Environment Configuration Guide

This document explains how to configure the Reddit API collector using environment variables in the `.env` file.

## 📋 Configuration Overview

The Reddit API collector reads configuration from the `.env` file, allowing you to customize:
- Target subreddits for data collection
- Keywords for content filtering
- Rate limiting parameters
- API credentials

## 🔧 Environment Variables

### Reddit API Credentials (Required)
```bash
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=YourApp:v1.0 (by /u/yourusername)
```

### Target Configuration (Optional)
```bash
# Subreddits to collect from (comma-separated, no spaces in names)
TARGET_SUBREDDITS=technology,artificial,chatgpt,openai,MachineLearning

# Keywords for filtering posts and comments (comma-separated)
TARGET_KEYWORDS=AI,claude,chatgpt,transformer,RAG,MCP
```

### Rate Limiting Configuration (Optional)
```bash
MAX_REQUESTS_PER_WINDOW=600
WINDOW_DURATION_MINUTES=10
BASE_DELAY=1.0
MAX_DELAY=60.0
MAX_RETRIES=5
CIRCUIT_BREAKER_THRESHOLD=5
```

### Database Configuration (Optional)
```bash
DATABASE_PATH=reddit_data.db
```

## ⚠️ Important Notes

### Subreddit Names
- **Do NOT include spaces** in subreddit names
- **Do NOT include the "r/" prefix**
- Use exact subreddit names as they appear in URLs

**Examples:**
```bash
# ✅ Correct
TARGET_SUBREDDITS=technology,MachineLearning,artificial

# ❌ Wrong - contains spaces
TARGET_SUBREDDITS=technology,artificial intelligence,machine learning

# ❌ Wrong - includes r/ prefix  
TARGET_SUBREDDITS=r/technology,r/MachineLearning
```

### Keywords
- Case-insensitive matching
- Partial word matching (e.g., "AI" matches "artificial intelligence")
- Use commas to separate keywords
- Spaces in individual keywords are allowed

## 🧪 Testing Configuration

Test your configuration:

```bash
# Test Reddit API connection
python scripts/collect-historical.py --test-connection

# Test configuration loading
uv run python -c "from reddit_api import create_config_from_env; print(create_config_from_env().target_subreddits)"
```

## 📝 Default Values

If environment variables are not set, the following defaults are used:

**Default Subreddits:**
- technology
- politics  
- investing
- MachineLearning

**Default Keywords:**
- AI
- interest rates
- EVs
- recession
- inflation

**Default Rate Limiting:**
- 600 requests per 10-minute window
- 1.0 second base delay
- 60 second maximum delay

## 🚀 Usage Examples

### Current Configuration (from .env)
The project is currently configured for AI and technology focus:

**Subreddits:**
- `r/technology` - General technology discussions
- `r/artificial` - Artificial intelligence topics
- `r/chatgpt` - ChatGPT discussions and use cases
- `r/openai` - OpenAI news and developments
- `r/MachineLearning` - Machine learning research and discussions

**Keywords:**
- `AI` - Artificial intelligence general
- `claude` - Claude AI assistant
- `chatgpt` - ChatGPT discussions
- `transformer` - Transformer models
- `RAG` - Retrieval-Augmented Generation
- `MCP` - Model Context Protocol

### Example Collections

```bash
# Collect using .env configuration
uv run python -m reddit_api.cli historical --days 7

# Override subreddits via command line
python scripts/collect-historical.py --days-back 30 --subreddits technology openai

# Override keywords via command line  
python scripts/collect-historical.py --days-back 14 --keywords "AI" "machine learning"
```

## 🔒 Security

- **Never commit your actual API credentials** to version control
- The `.env` file should be in `.gitignore`
- Use placeholder values in documentation
- Regenerate credentials if accidentally exposed

## 📚 Related Documentation

- [Historical Collection Guide](historical-collection.md) - Time frame-based data collection
- [README](../README.md) - Main project documentation
- [Module Documentation](../README_reddit_module.md) - Detailed API reference