# Show available recipes
default:
    @just --list --unsorted

# Run all available recipes
all: lint typecheck test coverage build docs-build

# Sync development dependencies (may update uv.lock if pyproject.toml changed)
sync *ARGS:
    uv sync {{ARGS}} --group dev

# Lint and format source code
lint:
    uv run ruff check --fix src/ tests/
    uv run ruff format src/ tests/

# Run static type checks with Astral ty
typecheck:
    uv run ty check src/

# Run tests
test *ARGS:
    uv run pytest -v {{ARGS}} tests/

# Run tests with coverage report
coverage:
    uv run pytest --cov=smartscan --cov-report=term-missing tests/

# Build distribution packages
build:
    uv build

# Serve documentation locally
docs-serve:
    uv run zensical serve

# Build documentation
docs-build:
    uv run zensical build

# Remove build artifacts
clean:
    rm -rf dist/ site/ .cache/ .ruff_cache/ .pytest_cache/ htmlcov/ .coverage
    find src/ tests/ -type f -name "*.pyc" -delete
    find src/ tests/ -type d -name "__pycache__" -delete
