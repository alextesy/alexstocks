# Testing Guide

This document describes the testing setup and strategy for the Market Pulse project.

## Test Structure

The test suite is organized into several categories:

### Unit Tests
- **Location**: `tests/test_*.py`
- **Purpose**: Test individual components in isolation
- **Scope**: Functions, classes, and methods
- **Speed**: Fast (< 1 second per test)

### Integration Tests
- **Location**: `tests/test_integration.py`
- **Purpose**: Test complete workflows and component interactions
- **Scope**: End-to-end pipeline testing
- **Speed**: Medium (1-10 seconds per test)

### Performance Tests
- **Location**: `tests/test_performance.py`
- **Purpose**: Test system performance and scalability
- **Scope**: Large datasets, memory usage, processing speed
- **Speed**: Slow (10+ seconds per test)

## Test Categories

### Reddit Scraping Tests (`test_reddit_scraping.py`)
Tests the Reddit data collection and parsing functionality:

- **RedditParser**: Post parsing, URL generation, content extraction
- **RedditDiscussionScraper**: Comment parsing, thread handling
- **RedditFullScraper**: Complete thread scraping
- **RedditIncrementalScraper**: Incremental updates
- **Real-world examples**: Meme language, emojis, Unicode handling

### Ticker Linking Tests (`test_ticker_linking.py`)
Tests the ticker identification and linking functionality:

- **TickerLinker**: Symbol matching, context analysis
- **TickerLinkDTO**: Data validation and structure
- **Real-world examples**: WallStreetBets language, technical analysis, earnings discussions
- **False positive prevention**: Avoiding incorrect matches

### Sentiment Analysis Tests (`test_sentiment_analysis.py`)
Tests the sentiment analysis services:

- **SentimentService**: VADER sentiment analysis
- **LLMSentimentService**: Hugging Face model integration
- **HybridSentimentService**: Dual model strategy
- **Real-world examples**: Meme language, financial terminology, sarcasm detection

### Integration Tests (`test_integration.py`)
Tests complete workflows:

- **Full pipeline**: Reddit scraping → ticker linking → sentiment analysis → database storage
- **Error handling**: Graceful failure handling
- **Database transactions**: Rollback on errors
- **Real-world scenarios**: Complete user workflows

### Performance Tests (`test_performance.py`)
Tests system performance:

- **Large datasets**: Processing 100+ articles
- **Memory usage**: Memory efficiency with large datasets
- **Processing speed**: Time benchmarks
- **Concurrent processing**: Multi-threading performance

## Running Tests

### Prerequisites
```bash
# Install dependencies
uv sync --dev

# Set up test environment
export DATABASE_URL="sqlite:///:memory:"
export REDDIT_CLIENT_ID="test_client_id"
export REDDIT_CLIENT_SECRET="test_client_secret"
export REDDIT_USER_AGENT="test_user_agent"
export SENTIMENT_USE_LLM="false"
export SENTIMENT_FALLBACK_VADER="true"
```

### Test Commands

```bash
# Run all tests
make test

# Run specific test categories
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-performance   # Performance tests only

# Run tests by functionality
make test-reddit        # Reddit-related tests
make test-sentiment     # Sentiment analysis tests
make test-linking       # Ticker linking tests

# Run with coverage
make test-coverage      # Generate coverage report

# Run fast tests only
make test-fast          # Exclude slow tests
```

### Individual Test Files
```bash
# Run specific test files
uv run pytest tests/test_reddit_scraper.py -v
uv run pytest tests/test_ticker_linking.py -v
uv run pytest tests/test_sentiment_analysis.py -v
uv run pytest tests/test_integration.py -v
uv run pytest tests/test_performance.py -v
```

### Test Markers
```bash
# Run tests by markers
uv run pytest -m "integration" -v
uv run pytest -m "performance" -v
uv run pytest -m "not slow" -v
uv run pytest -m "reddit" -v
uv run pytest -m "llm" -v
```

## Test Configuration

### Pytest Configuration (`pyproject.toml`)
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

### Test Fixtures (`tests/conftest.py`)
- **Database fixtures**: In-memory SQLite for testing
- **Mock services**: Reddit API, sentiment analysis
- **Sample data**: Tickers, articles, Reddit submissions
- **Environment setup**: Test environment variables

## Test Data

### Sample Tickers
- AAPL, TSLA, NVDA, GME, AMC, SPY, QQQ, MSFT, GOOGL, AMZN

### Sample Articles
- WallStreetBets meme posts
- Technical analysis discussions
- Earnings discussions
- Reddit comments with ticker mentions

### Mock Reddit Data
- Realistic submission structures
- Comment hierarchies
- User interactions (upvotes, comments)

## CI/CD Integration

### GitHub Actions (`/.github/workflows/ci.yml`)
The CI pipeline includes:

1. **Test Suite**: Unit, integration, and performance tests
2. **Linting**: Ruff, Black, MyPy
3. **Security**: Bandit security scanning
4. **Build**: Package building and Docker image creation
5. **Coverage**: Code coverage reporting

### Test Environment
- **Database**: PostgreSQL service
- **Dependencies**: Cached for faster builds
- **Parallel execution**: Multiple test jobs
- **Artifact collection**: Test reports and coverage

## Best Practices

### Writing Tests
1. **Use descriptive names**: `test_reddit_parser_with_meme_language`
2. **Test real scenarios**: Use realistic Reddit content
3. **Mock external dependencies**: Reddit API, LLM models
4. **Test edge cases**: Empty content, malformed data
5. **Verify both success and failure paths**

### Test Organization
1. **One test class per module**: `TestRedditParser`, `TestTickerLinker`
2. **Group related tests**: All Reddit tests in one file
3. **Use fixtures for common setup**: Database, mock services
4. **Mark slow tests**: Use `@pytest.mark.slow`

### Performance Testing
1. **Set reasonable timeouts**: < 5 seconds for most tests
2. **Test with realistic data sizes**: 100+ articles
3. **Measure memory usage**: Monitor for memory leaks
4. **Benchmark improvements**: Track performance over time

## Troubleshooting

### Common Issues

#### Database Connection Errors
```bash
# Ensure test database is available
export DATABASE_URL="sqlite:///:memory:"
```

#### Missing Dependencies
```bash
# Install all test dependencies
uv sync --dev
```

#### Slow Tests
```bash
# Run only fast tests
make test-fast
```

#### Memory Issues
```bash
# Run performance tests individually
uv run pytest tests/test_performance.py::TestPerformance::test_memory_usage_performance -v
```

### Debug Mode
```bash
# Run tests with debug output
uv run pytest tests/ -v -s --tb=long

# Run specific test with debug
uv run pytest tests/test_reddit_scraper.py::TestRedditParser::test_parse_submission -v -s
```

## Coverage

### Coverage Reports
```bash
# Generate HTML coverage report
make test-coverage

# View coverage report
open htmlcov/index.html
```

### Coverage Goals
- **Unit tests**: > 90% coverage
- **Integration tests**: > 80% coverage
- **Critical paths**: 100% coverage

## Continuous Integration

The CI pipeline runs on every push and pull request:

1. **Linting**: Code quality checks
2. **Unit Tests**: Fast feedback
3. **Integration Tests**: End-to-end validation
4. **Performance Tests**: Performance regression detection
5. **Security Scan**: Vulnerability detection
6. **Build**: Package and Docker image creation

### Local CI Simulation
```bash
# Run the same checks as CI
make lint
make test
make security
```

## Contributing

When adding new tests:

1. **Follow naming conventions**: `test_<functionality>_<scenario>`
2. **Add appropriate markers**: `@pytest.mark.integration`, `@pytest.mark.performance`
3. **Update this documentation**: Add new test categories
4. **Ensure CI passes**: All tests must pass before merging
5. **Add real-world examples**: Use realistic test data

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Python Testing Best Practices](https://docs.python.org/3/library/unittest.html)
- [Mock Documentation](https://docs.python.org/3/library/unittest.mock.html)
- [Coverage.py Documentation](https://coverage.readthedocs.io/)

