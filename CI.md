# AIOS CI/CD Pipeline

AIOS uses GitHub Actions for continuous integration and delivery, running automated tests, linting, security scans, and Docker builds on every push and pull request.

## Overview

The CI pipeline includes four parallel jobs:

```
┌─────────────────────────────────────────────────────┐
│                  Push / Pull Request                 │
└────┬──────────┬──────────────┬──────────────┬───────┘
     │          │              │              │
     ▼          ▼              ▼              ▼
┌─────────┐ ┌───────┐ ┌───────────┐ ┌──────────────┐
│  Tests  │ │ Lint  │ │ Security  │ │    Docker     │
│ (3 Py   │ │ Black │ │ Bandit    │ │ Build & Test  │
│ versions│ │ isort │ │ Safety    │ │               │
│ + cov)  │ │ flake8│ │           │ │               │
└─────────┘ └───────┘ └───────────┘ └──────────────┘
```

## Workflow Configuration

The workflow is defined in `.github/workflows/test.yml`.

### Triggers

The pipeline runs on:
- **Push** to `master`, `main`, or `develop` branches
- **Pull requests** targeting `master`, `main`, or `develop`

## Jobs

### 1. Tests

Runs the full test suite across multiple Python versions.

| Setting | Value |
|---------|-------|
| Runner | `ubuntu-latest` |
| Python versions | 3.10, 3.11, 3.12 |
| Test framework | pytest |
| Coverage | pytest-cov (XML + terminal) |

**Steps:**
1. Checkout code
2. Set up Python (matrix strategy)
3. Cache pip dependencies
4. Install project + test dependencies
5. Run `pytest tests/ -v --cov=aios --cov-report=xml`
6. Upload coverage to Codecov (Python 3.11 only)

**Dependencies installed:**
```
pytest
pytest-cov
pytest-asyncio
```

### 2. Lint

Checks code quality and formatting.

| Tool | Purpose |
|------|---------|
| **Black** | Code formatting check |
| **isort** | Import sorting check |
| **flake8** | Syntax errors, undefined names, complexity |

**flake8 configuration:**
- Hard fail on: syntax errors (`E9`), `__future__` issues (`F63`), undefined names (`F7`, `F82`)
- Warning only: all other issues, max complexity 10, max line length 100

### 3. Security

Scans for security vulnerabilities.

| Tool | Purpose |
|------|---------|
| **Bandit** | Static security analysis of Python code |
| **Safety** | Checks dependencies for known vulnerabilities |

**Bandit settings:**
- Scans `aios/` directory
- Low-low severity threshold (`-ll -ii`)
- Excludes test files

### 4. Docker

Validates the Docker build.

**Steps:**
1. Set up Docker Buildx
2. Build the Docker image (no push)
3. Test the image by importing the `aios` package
4. Uses GitHub Actions cache for faster builds

## Running Locally

### Run Tests

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-asyncio

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=aios --cov-report=term-missing
```

### Run Linting

```bash
# Install linting tools
pip install black isort flake8

# Check formatting
black --check --diff aios/

# Check import sorting
isort --check-only --diff aios/

# Run flake8
flake8 aios/ --max-complexity=10 --max-line-length=100
```

### Fix Formatting

```bash
# Auto-format code
black aios/

# Auto-sort imports
isort aios/
```

### Run Security Scans

```bash
# Install security tools
pip install bandit safety

# Run Bandit
bandit -r aios/ -ll -ii -x tests/

# Check dependencies
safety check
```

## Coverage

Code coverage is collected during the test job and uploaded to [Codecov](https://codecov.io/) for the Python 3.11 run. This provides:

- Per-file coverage reports
- PR coverage diff comments
- Coverage trend tracking
- Missing line identification

## Adding New Tests

When adding new features, include tests:

1. Create `tests/test_<feature>.py`
2. Follow the existing test patterns (see `tests/conftest.py` for fixtures)
3. Ensure tests pass locally: `pytest tests/test_<feature>.py -v`
4. The CI pipeline will automatically run your tests on push

### Test file naming convention:

| Module | Test File |
|--------|-----------|
| `aios/cache.py` | `tests/test_cache.py` |
| `aios/plugins.py` | `tests/test_plugins.py` |
| `aios/ratelimit.py` | `tests/test_ratelimit.py` |
| `aios/credentials.py` | `tests/test_credentials.py` |
| `aios/context/session.py` | `tests/test_session.py` |

## Troubleshooting

### Tests fail in CI but pass locally

- Check Python version differences (CI tests 3.10, 3.11, 3.12)
- Check for platform-specific behavior (CI runs Ubuntu, local may differ)
- Check for missing test dependencies

### Lint failures

- Run `black aios/` and `isort aios/` locally before committing
- Check flake8 output for syntax errors (these are hard failures)

### Security scan findings

- Bandit findings are warnings by default (non-blocking)
- Safety findings indicate vulnerable dependencies - update `requirements.txt`
- Review findings in the Actions tab for details

### Docker build failures

- Check `Dockerfile` for syntax errors
- Ensure all required files are not in `.dockerignore`
- Test locally: `docker build -t aios:test .`
