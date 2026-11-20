# Reddit Analyzer

A local research tool for exploring AI and technology discussions on Reddit. It collects public posts and comments, preserves the source records, and computes sentiment, topics, time series, forecasts, and evidence-backed analysis artifacts for a dashboard.

## 📋 Project Overview

The batch pipeline uses SQLite by default and can mirror a completed run to Neon when configured. Model predictions carry an artifact fingerprint; changing the sentiment model requires an explicit rescore. Weak labels are training aids, while independent human labels are required before reporting sentiment accuracy or promoting a replacement model.

## Pipeline refresh and evaluation

Run the routine refresh from the repository root:

```bash
./scripts/run_pipeline.sh --refresh
```

Refreshes process new records and reuse existing model artifacts. A full rebuild, including explicit training and topic refitting, is opt-in:

```bash
./scripts/run_pipeline.sh --full-rebuild --all
```

Individual operations remain available with `--step N` (or `step N`). Use `--check` for gate and freshness status and `--no-neon-sync` to keep a run local.
Step 4 stages a candidate sentiment model. Step 5 rescores and promotes that candidate together with its predictions. A full rebuild runs both steps, and a routine refresh reuses the active model.

Create an annotation-ready sample and reports without training or collection:

```bash
python scripts/sample_evaluation_set.py --db historical_reddit_data.db
python scripts/evaluate_sentiment.py --sample data/sentiment_evaluation_sample.csv --reference data/sentiment_evaluation_sample_reference.csv
python scripts/report_topic_diagnostics.py --db historical_reddit_data.db --run-version runtime_luna-v1
python scripts/backtest_forecasts.py --db historical_reddit_data.db
```

The sample is approximately 250 rows, stratified by community, time, content type, and VADER class. It reserves thread/time holdouts and leaves `human_label` blank. The annotation CSV contains original title/text/source URL and is blinded from model/VADER labels; the separate reference CSV is used only when scoring. Until labels are independently reviewed, the sentiment report remains explicitly unverified; VADER agreement is reported separately from model accuracy. Topic diagnostics include original representative text and require manual review before labels can be promoted.

### Enable pipeline execution in the dashboard

1. From the repository root, run `openssl rand -hex 32` to generate an operator token. Add the output to the local `.env` file as `PIPELINE_OPERATOR_TOKEN=<generated-token>`. If `.env` already has a token value, use it. Keep the token in `.env`, which Git ignores.
2. Start the dashboard and backend with `./scripts/startup.sh`. Restart them after changing `.env`.
3. Open `http://localhost:3000/pipeline` and choose a step, **Refresh pipeline**, or **Rebuild pipeline**. With the default local startup, the dashboard server reads the token from `.env` automatically, including after page reloads.

For a dashboard started outside the local startup script or bound to a network interface, enter the token in the **Operator token** field. On macOS, use this command from the repository root to copy the saved token to your clipboard.

```bash
sed -n 's/^PIPELINE_OPERATOR_TOKEN=//p' .env | pbcopy
```

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
- **Historical Data Collection**: Time frame-based collection with progress tracking
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

# Collect historical data (last 30 days)
uv run python -m reddit_api.cli historical --days 30

# Collect data for specific date range
python scripts/collect-historical.py --start-date "2024-01-01" --end-date "2024-01-31"

# Run example scripts
uv run python example_usage.py
uv run python example_historical_collection.py

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
- **[Historical Collection Guide](docs/historical-collection.md)** - Time frame-based data collection
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
