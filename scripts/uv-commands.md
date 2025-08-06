# UV Commands Reference

Quick reference for using uv with the Reddit API Collector project.

## Installation & Setup

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run development setup script
./scripts/dev-setup.sh

# Or manual setup:
uv venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate    # Windows
```

## Dependency Management

```bash
# Install project with core dependencies
uv pip install -e .

# Install with all optional dependencies
uv pip install -e ".[dev,ml,production]"

# Install specific optional groups
uv pip install -e ".[dev]"        # Development tools
uv pip install -e ".[ml]"         # Machine learning libs
uv pip install -e ".[production]" # Production deployment

# Add new dependency to pyproject.toml and install
uv add requests>=2.30.0

# Add development dependency
uv add --dev pytest>=7.0.0

# Update all dependencies
uv lock --upgrade

# Install from lock file (production)
uv pip sync uv.lock
```

## Project Commands

```bash
# Run the application
uv run python example_usage.py

# Test Reddit API connection
uv run python -m reddit_api.cli test

# Collect Reddit data
uv run python -m reddit_api.cli collect --posts 10 --comments 5

# Run with specific Python version
uv run --python 3.11 python example_usage.py

# Run Jupyter notebook
uv run jupyter notebook notebooks/reddit_api_prototype.ipynb
```

## Development Workflow

```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=reddit_api

# Code formatting
uv run black src/ tests/
uv run isort src/ tests/

# Type checking
uv run mypy src/reddit_api/

# Linting
uv run flake8 src/ tests/

# All quality checks
uv run pre-commit run --all-files
```

## Virtual Environment Management

```bash
# Create virtual environment
uv venv

# Create with specific Python version
uv venv --python 3.11

# Activate environment
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate    # Windows

# Deactivate
deactivate

# Remove virtual environment
rm -rf .venv
```

## Package Building & Distribution

```bash
# Build package
uv build

# Build wheel only
uv build --wheel

# Build source distribution only
uv build --sdist

# Install from built package
uv pip install dist/reddit_api_collector-1.0.0-py3-none-any.whl
```

## Lock File Management

```bash
# Generate/update lock file
uv lock

# Install exact versions from lock file
uv pip sync

# Update specific package
uv lock --upgrade-package praw

# Check for outdated packages
uv pip list --outdated
```

## Environment Variables

```bash
# Run with environment file
uv run --env-file .env python example_usage.py

# Set environment variables inline
uv run --env REDDIT_CLIENT_ID=your_id python example_usage.py
```

## Troubleshooting

```bash
# Check uv version
uv --version

# Show installed packages
uv pip list

# Show package information
uv pip show praw

# Check for dependency conflicts
uv pip check

# Clear cache
uv cache clean

# Verbose output for debugging
uv --verbose pip install -e .
```

## Migration from pip/conda

```bash
# Before (pip)
pip install -r requirements.txt
pip install -e .

# After (uv)
uv pip install -e .
# or
uv pip sync uv.lock

# Before (conda)
conda env create -f environment.yaml

# After (uv)
uv venv --python 3.11
uv pip install -e ".[dev,ml]"
```

## Production Deployment

```bash
# Create production environment
uv venv --python 3.11
source .venv/bin/activate

# Install exact versions for reproducibility
uv pip sync uv.lock

# Or install production extras only
uv pip install -e ".[production]"

# Verify installation
uv run python -c "import reddit_api; print('✅ Installation successful')"
```

## Tips & Best Practices

1. **Always use lock files** in production for reproducible builds
2. **Pin Python version** in CI/CD and production environments
3. **Use optional dependencies** to keep core package lightweight
4. **Regular updates**: Run `uv lock --upgrade` periodically
5. **Environment isolation**: Always use virtual environments
6. **Git integration**: Commit both pyproject.toml and uv.lock files