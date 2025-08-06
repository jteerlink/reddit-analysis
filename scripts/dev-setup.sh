#!/bin/bash
# Development setup script using uv

set -e

echo "🚀 Setting up Reddit API Collector development environment with uv"
echo "================================================================"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi

echo "✅ Using uv version: $(uv --version)"

# Create virtual environment and install dependencies
echo "📦 Creating virtual environment and installing dependencies..."
uv venv
source .venv/bin/activate

# Install all dependencies including dev dependencies
echo "📥 Installing project with all dependencies..."
uv pip install -e ".[dev,ml]"

# Install pre-commit hooks
echo "🔧 Setting up pre-commit hooks..."
pre-commit install

# Create .env file from template if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file template..."
    cat > .env << EOF
# Reddit API Credentials
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=YourApp:v1.0 (by /u/yourusername)

# Target Configuration
TARGET_SUBREDDITS=technology,MachineLearning,artificial
TARGET_KEYWORDS=AI,machine learning,artificial intelligence,inflation,economics

# Optional: Database Configuration
DATABASE_PATH=reddit_data.db

# Optional: Rate Limiting
MAX_REQUESTS_PER_WINDOW=600
RATE_LIMIT_WINDOW=600
EOF
    echo "⚠️  Please edit .env file with your Reddit API credentials"
fi

echo "✅ Development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your Reddit API credentials"
echo "2. Get credentials from: https://www.reddit.com/prefs/apps"
echo "3. Run: python example_usage.py"
echo "4. Or use: uv run python -m reddit_api.cli test"