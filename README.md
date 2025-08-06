# Inflation Forecasting Project

A comprehensive system for forecasting inflation trends through social media sentiment analysis on Reddit data.

## 📋 Project Overview

This project collects and analyzes Reddit discussions to extract sentiment patterns related to economic indicators and inflation trends. Originally specified in the Product Requirements Document (PRD), the system has evolved into a production-ready Python package with modern tooling.

## 🚀 Quick Start with UV (Recommended)

This project uses [uv](https://github.com/astral-sh/uv) for fast, reliable Python package management.

```bash
# Clone the repository
git clone https://github.com/your-username/inflation-forcasting.git
cd inflation-forcasting

# Run automated development setup
chmod +x scripts/dev-setup.sh
./scripts/dev-setup.sh

# Test the installation
uv run python example_usage.py
```

## 📁 Project Structure

```
├── docs/                           # Documentation
│   └── prd.md                     # Product Requirements Document
├── notebooks/                     # Jupyter notebooks for exploration
│   └── reddit_api_prototype.ipynb # Original prototype
├── src/reddit_api/               # Main Python package
│   ├── models.py                 # Data models
│   ├── client.py                 # Rate-limited Reddit client
│   ├── collector.py              # Data collection logic
│   ├── storage.py                # Database operations
│   ├── main.py                   # High-level orchestration
│   └── cli.py                    # Command-line interface
├── scripts/                      # Development scripts
│   ├── dev-setup.sh             # Automated development setup
│   └── uv-commands.md           # UV command reference
├── pyproject.toml               # Modern Python project configuration
├── uv.lock                      # Dependency lock file
├── example_usage.py             # Usage examples
└── README_reddit_module.md      # Detailed module documentation
```

## 🛠 Package Management Migration

This project has been **migrated from traditional pip/conda to uv** for improved dependency management:

### Before (Legacy)
- `requirements.txt` - pip dependencies
- `setup.py` - package configuration  
- `setup/environment.yaml` - conda environment

### After (Modern)
- `pyproject.toml` - unified project configuration
- `uv.lock` - locked dependency versions
- `scripts/dev-setup.sh` - automated environment setup

## 🔄 Migration Benefits

**Why UV?**
- **10-100x faster** dependency resolution than pip
- **Reproducible builds** with lockfiles
- **Better caching** and parallel downloads
- **Modern Python standards** (PEP 518/621)
- **Drop-in replacement** for existing pip workflows

## 📦 Installation Options

### Option 1: UV (Recommended)
```bash
# Development environment with all features
uv venv
source .venv/bin/activate  # Linux/Mac
uv pip install -e ".[dev,ml]"

# Or use the automated script
./scripts/dev-setup.sh
```

### Option 2: Traditional Pip (Still Supported)
```bash
# Core installation
pip install -e .

# With optional dependencies
pip install -e ".[dev,ml]"
```

### Option 3: Production Deployment
```bash
# Exact reproducible installation
uv venv --python 3.11
uv pip sync uv.lock
```

## 🎯 Key Features

- **Rate-Limited Reddit API Client**: Respects 600 requests/10min limit
- **Circuit Breaker Pattern**: Fault tolerance with automatic recovery
- **SQLite Storage**: Optimized schema with analytics functions
- **CLI Interface**: Easy data collection and management
- **Modular Architecture**: Extensible for sentiment analysis pipeline
- **Type Safety**: Full type hints with mypy validation
- **Modern Packaging**: PEP 621 compliant with optional dependencies

## 💻 Usage Examples

```bash
# Test Reddit API connection
uv run python -m reddit_api.cli test

# Collect Reddit data
uv run python -m reddit_api.cli collect --posts 10 --comments 5

# Run example script
uv run python example_usage.py

# Start Jupyter notebook
uv run jupyter notebook notebooks/reddit_api_prototype.ipynb
```

## 🔧 Development Workflow

```bash
# Code quality checks
uv run black src/ tests/        # Format code
uv run isort src/ tests/        # Sort imports
uv run mypy src/reddit_api/     # Type checking
uv run flake8 src/ tests/       # Linting

# Testing
uv run pytest                   # Run tests
uv run pytest --cov=reddit_api # With coverage

# Dependency management
uv add requests>=2.30.0         # Add dependency
uv lock --upgrade               # Update lockfile
```

## 📊 Performance & Scaling

- **Storage**: ~500KB per 1000 posts (SQLite)
- **Rate Limiting**: 1 request/second with exponential backoff
- **Memory**: Streaming processing, minimal footprint
- **Scaling**: Ready for PostgreSQL/TimescaleDB upgrade

## 🔒 Security & Privacy

- **Read-Only API**: No user authentication required
- **Public Data**: Only publicly available Reddit content
- **Local Storage**: SQLite database, no cloud dependencies
- **Rate Limiting**: Respects Reddit's Terms of Service

## 📈 Production Considerations

For production deployment:

1. **Database**: Migrate to PostgreSQL/TimescaleDB
2. **Monitoring**: Add comprehensive metrics and alerting
3. **Caching**: Implement Redis for session management
4. **Scaling**: Horizontal scaling with load balancing
5. **Security**: Secrets management and API authentication

## 🤝 Integration

This module integrates seamlessly with:
- **Sentiment Analysis**: VADER, TextBlob, or custom models
- **Dashboard**: Streamlit, Plotly, or custom visualization
- **MLOps**: MLflow, Evidently for model monitoring
- **APIs**: FastAPI for real-time data serving

## 📚 Documentation

- **[Module Documentation](README_reddit_module.md)** - Detailed API reference
- **[UV Commands](scripts/uv-commands.md)** - Package management reference
- **[PRD Document](docs/prd.md)** - Original requirements and architecture
- **[Example Notebook](notebooks/reddit_api_prototype.ipynb)** - Interactive exploration

## 🐛 Troubleshooting

Common issues and solutions:

1. **Authentication**: Check Reddit API credentials in `.env`
2. **Rate Limiting**: Normal behavior, requests are queued automatically
3. **Dependencies**: Use `uv lock --upgrade` to update packages
4. **Environment**: Ensure virtual environment is activated

## 🏆 Next Steps

1. **Sentiment Analysis**: Integrate with ML models for economic sentiment
2. **Real-Time Streaming**: Add websocket-based live data collection
3. **Dashboard**: Build interactive visualization for inflation trends
4. **Deployment**: Containerize for production deployment

## 📧 Support

For questions and issues:
1. Check documentation in `README_reddit_module.md`
2. Review UV commands in `scripts/uv-commands.md` 
3. Test with `uv run python example_usage.py`
4. Open GitHub issues with logs and configuration

---

**Ready for inflation forecasting through social media sentiment analysis!** 🚀