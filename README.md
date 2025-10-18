# AlexStocks

**A production-ready market sentiment analytics platform that tracks real-time discussions and sentiment across financial markets.**

AlexStocks is a comprehensive web application that collects, analyzes, and visualizes market sentiment from Reddit discussions. It uses advanced NLP techniques including FinBERT-based sentiment analysis and intelligent ticker linking to provide actionable insights into market trends and momentum.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://www.postgresql.org/)

> 🚀 **NEW**: ECS Fargate migration complete! Cron jobs now run as containerized tasks on AWS Fargate (Spot) for 90% cost savings. See [ECS_MIGRATION_SUMMARY.md](ECS_MIGRATION_SUMMARY.md) for details.

---

## 🚀 Features

### Core Capabilities
- **📊 Real-Time Sentiment Tracking**: Dual-model sentiment analysis using FinBERT (financial domain) + VADER (social context)
- **🔍 Intelligent Ticker Linking**: Advanced NLP-based ticker extraction with context awareness and alias matching
- **📈 Live Stock Price Integration**: Real-time and historical stock price data via yfinance API
- **🎯 Momentum Detection**: Velocity metrics showing discussion volume trends and spikes
- **💬 Reddit Integration**: Automated scraping of r/wallstreetbets, r/stocks, and r/investing discussions
- **📉 Interactive Visualizations**: Sentiment histograms, time-series charts, and price correlation graphs
- **🔄 Incremental Processing**: Efficient data pipeline with deduplication and rate limiting

### Analytics & Insights
- **Sentiment Distribution**: Histogram visualization of positive/negative/neutral sentiment
- **Temporal Analysis**: Track sentiment trends over time for any ticker
- **Volume Metrics**: 24-hour discussion velocity with baseline comparisons
- **Multi-Source Data**: Aggregate sentiment from daily discussion threads and individual posts
- **Confidence Scoring**: Context-aware ticker matching with relevance scores

---

## 🏗️ Architecture

### Technology Stack

**Backend:**
- **FastAPI** - High-performance async web framework
- **SQLAlchemy 2.0** - Modern ORM with async support
- **PostgreSQL 16** - Primary data store with JSONB support
- **Pydantic** - Data validation and settings management

**Data Processing:**
- **FinBERT** - Financial sentiment analysis (ProsusAI/finbert)
- **VADER** - Social media sentiment analysis
- **PRAW** - Reddit API integration
- **yfinance** - Real-time stock price data
- **Beautiful Soup** - HTML parsing for content extraction

**Frontend:**
- **Jinja2 Templates** - Server-side rendering
- **Tailwind CSS** - Utility-first styling
- **Chart.js** - Interactive data visualization

**Development:**
- **uv** - Fast Python package management
- **Docker & Docker Compose** - Containerized deployment
- **pytest** - Comprehensive test suite
- **Ruff & Black** - Code formatting and linting
- **MyPy** - Static type checking

**Infrastructure (Production):**
- **AWS ECS Fargate** - Serverless container orchestration
- **EventBridge Scheduler** - Cron job scheduling
- **CloudWatch Logs** - Centralized logging
- **Terraform** - Infrastructure as code
- **GitHub Actions** - CI/CD pipeline

### Database Schema

```
┌─────────────┐         ┌──────────────────┐         ┌─────────────┐
│   Ticker    │         │  ArticleTicker   │         │   Article   │
├─────────────┤         ├──────────────────┤         ├─────────────┤
│ symbol (PK) │◄─────── ┤ ticker (FK)      │         │ id (PK)     │
│ name        │         │ article_id (FK)  ├────────►│ source      │
│ aliases     │         │ confidence       │         │ url         │
│ exchange    │         │ matched_terms    │         │ title       │
│ is_sp500    │         └──────────────────┘         │ text        │
└─────────────┘                                      │ sentiment   │
                                                     │ published_at│
┌──────────────────┐                                 │ reddit_id   │
│   StockPrice     │                                 │ subreddit   │
├──────────────────┤                                 │ author      │
│ symbol (FK)      │                                 │ upvotes     │
│ price            │                                 └─────────────┘
│ change           │
│ change_percent   │         ┌─────────────────────┐
│ market_state     │         │ StockPriceHistory   │
│ updated_at       │         ├─────────────────────┤
└──────────────────┘         │ symbol (FK)         │
                             │ date                │
                             │ close_price         │
                             │ volume              │
                             └─────────────────────┘
```

---

## 📦 Quick Start

### Prerequisites

- **Python 3.11+** (required for modern type hints)
- **[uv](https://docs.astral.sh/uv/)** package manager
- **Docker & Docker Compose** (for PostgreSQL)
- **Reddit API credentials** (see [Reddit Setup](#reddit-api-setup))

### Installation

1. **Clone and navigate to the project:**
   ```bash
   git clone <repository-url>
   cd market-pulse-v2
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Configure environment variables:**
   ```bash
   cp env.example .env
   # Edit .env with your Reddit API credentials
   ```

4. **Start PostgreSQL:**
   ```bash
   make up
   ```

5. **Initialize database and seed data:**
   ```bash
   make db-init
   make seed-tickers
   ```

6. **Optional: Add sample data for demo:**
   ```bash
   make seed-sample-data
   ```

### Access the Application

- **Web Interface**: http://localhost:8000/
- **Browse Tickers**: http://localhost:8000/browse
- **Ticker Details**: http://localhost:8000/t/AAPL
- **Health Check**: http://localhost:8000/health
- **API Docs**: http://localhost:8000/docs

---

## 🎯 Usage

### Data Collection

```bash
# Scrape Reddit discussions from daily threads
make reddit-robust-scrape              # Single latest thread
make reddit-robust-scrape-multi        # Multiple threads (last 3 days)

# Analyze sentiment for new articles
make analyze-sentiment                 # All unanalyzed articles
make analyze-sentiment-recent          # Last 24 hours only

# Collect stock price data
make collect-stock-prices              # Current prices
make collect-historical-data           # Historical OHLCV data
make collect-both-stock-data           # Both current + historical

# Combined pipeline (scrape + analyze)
make scrape-and-analyze-full
```

### Reddit Data Sources

The platform targets three major finance subreddits:

- **r/wallstreetbets**: High-volume meme stock discussions, strong sentiment signals
- **r/stocks**: General stock market discussions, balanced perspectives
- **r/investing**: Long-term investment focus, fundamental analysis

### Sentiment Analysis

**Dual-Model Approach:**
- **FinBERT** (ProsusAI/finbert): Financial domain-specific sentiment (0.65 weight)
- **VADER**: Social media context and slang (0.35 weight)
- **Adaptive Scoring**: Stronger sentiment signals when models agree

```bash
# Override existing sentiment with dual-model analysis
make override-sentiment-dual           # All articles
make override-sentiment-dual-reddit    # Reddit only
make override-sentiment-dual-recent    # Last 24h only
```

---

## 🔧 Development

### Available Commands

```bash
make help                    # Show all available commands

# Development
make up                      # Start services (Postgres + API)
make down                    # Stop all services
make clean                   # Clean containers and volumes

# Database
make db-init                 # Initialize schema
make seed-tickers            # Seed ticker data (~58 core tickers)
make query-db                # Query database (interactive)

# Testing
make test                    # Run all tests
make test-unit              # Unit tests only
make test-integration       # Integration tests only
make test-coverage          # Coverage report
make test-reddit            # Reddit-specific tests
make test-sentiment         # Sentiment analysis tests

# Code Quality
make lint                    # Run all linters
make lint-fix               # Auto-fix issues
make format                 # Format code (black + ruff)
make security               # Security audit (bandit)
```

### Project Structure

```
market-pulse-v2/
├── app/
│   ├── main.py                    # FastAPI application & routes
│   ├── config.py                  # Settings & environment config
│   ├── db/
│   │   ├── models.py             # SQLAlchemy ORM models
│   │   └── session.py            # Database session management
│   ├── services/
│   │   ├── sentiment.py          # VADER sentiment analysis
│   │   ├── llm_sentiment.py      # FinBERT sentiment analysis
│   │   ├── hybrid_sentiment.py   # Dual-model sentiment fusion
│   │   ├── velocity.py           # Discussion momentum metrics
│   │   ├── stock_data.py         # Stock price integration
│   │   └── context_analyzer.py   # Ticker context validation
│   ├── collectors/
│   │   └── stock_price_collector.py  # Price data collection
│   ├── jobs/
│   │   ├── analyze_sentiment.py      # Batch sentiment analysis
│   │   ├── collect_stock_prices.py   # Stock data jobs
│   │   └── scrape_monthly_discussions.py  # Reddit scraping
│   ├── scripts/
│   │   ├── init_db.py            # Database initialization
│   │   ├── seed_tickers.py       # Ticker seeding
│   │   └── [migrations...]       # Database migrations
│   └── templates/
│       ├── base.html             # Base template
│       ├── home.html             # Ticker grid homepage
│       ├── ticker.html           # Individual ticker page
│       └── browse.html           # Ticker browser
├── ingest/
│   ├── reddit.py                 # Reddit ingestion CLI
│   ├── reddit_parser.py          # Reddit post parsing
│   ├── reddit_robust_scraper.py  # Robust Reddit scraper
│   ├── linker.py                 # Ticker linking engine
│   └── [other scrapers...]
├── tests/
│   ├── test_main.py              # API endpoint tests
│   ├── test_sentiment.py         # Sentiment analysis tests
│   ├── test_reddit_ingest.py     # Reddit ingestion tests
│   ├── test_ticker_linking.py    # Ticker linking tests
│   └── conftest.py               # Test fixtures
├── data/
│   ├── tickers_core.csv          # Core ticker universe
│   └── aliases.yaml              # Ticker alias mappings
├── docs/                         # Detailed documentation
├── pyproject.toml                # Project dependencies
├── docker-compose.yml            # Service definitions
├── Makefile                      # Development commands
└── README.md                     # This file
```

---

## 🔑 Reddit API Setup

### 1. Create Reddit Application

1. Visit https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Fill in details:
   - **Name**: AlexStocks
   - **App type**: script
   - **Description**: Market sentiment analytics
   - **Redirect URI**: http://localhost:8080

### 2. Configure Credentials

Add to your `.env` file:

```bash
# Reddit API Configuration
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USER_AGENT=AlexStocks/1.0 by YourUsername
```

### 3. Test Connection

```bash
# Add Reddit-specific database columns (one-time)
make add-reddit-columns
make add-reddit-thread-table

# Test Reddit scraping
make reddit-robust-scrape --verbose
```

**Note:** The Reddit API has a rate limit of 60 requests/minute. The scraper implements automatic backoff and incremental saving to handle this gracefully.

---

## 📊 API Endpoints

### Core Routes

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/` | GET | Homepage with top 50 tickers (24h activity) |
| `/browse` | GET | Browse all tickers with search & sorting |
| `/t/{ticker}` | GET | Ticker detail page with articles |

### Data API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tickers` | GET | Paginated ticker list with filters |
| `/api/ticker/{ticker}/articles` | GET | Paginated articles for ticker |
| `/api/stock/{symbol}` | GET | Current stock price data |
| `/api/stock/{symbol}/chart` | GET | Historical price chart data |
| `/api/sentiment/histogram` | GET | Sentiment distribution data |
| `/api/sentiment/time-series` | GET | Sentiment over time for ticker |

### Query Parameters

**Pagination:**
- `page` - Page number (default: 1)
- `limit` - Items per page (default: 50)

**Filtering:**
- `search` - Search ticker symbols
- `sort_by` - Sort order: `recent_activity`, `alphabetical`, `total_articles`
- `days` - Time period for time-series data

---

## 🧪 Testing

### Test Suite

The project includes comprehensive tests covering:

- **Unit Tests**: Service logic, data processing, sentiment analysis
- **Integration Tests**: Database operations, API endpoints
- **Real-World Tests**: End-to-end workflows with actual data
- **Performance Tests**: Load testing, query optimization

```bash
# Run specific test categories
make test-unit              # Fast unit tests
make test-integration       # Integration tests
make test-real-world        # Real-world scenarios
make test-performance       # Performance benchmarks

# Coverage reporting
make test-coverage          # Generate HTML coverage report
```

### Test Configuration

Tests use:
- **pytest** with async support
- **pytest-mock** for mocking external APIs
- **Faker** for test data generation
- **freezegun** for time-based testing

---

## 🚀 Deployment

### Production Environment

**Live Site:** [alexstocks.com](https://alexstocks.com)

**Infrastructure:**
- **Web Application**: AWS EC2 (Ubuntu) + Nginx + FastAPI
- **Database**: PostgreSQL 16 (Docker on EC2)
- **Batch Jobs**: AWS ECS Fargate (Spot) ⭐ NEW
- **Scheduling**: EventBridge Scheduler ⭐ NEW
- **Container Registry**: Amazon ECR ⭐ NEW
- **SSL**: Let's Encrypt (auto-renewal)
- **Process Manager**: systemd
- **Logging**: CloudWatch Logs ⭐ NEW

**Deployment Process:**
1. **Web App**: Code pushed → GitHub Actions → Deploy to EC2 → Systemd restart
2. **Batch Jobs**: Code pushed → GitHub Actions → Build Docker → Push to ECR → Update ECS tasks ⭐ NEW

See deployment documentation:
- [ECS_MIGRATION_SUMMARY.md](ECS_MIGRATION_SUMMARY.md) - ECS Fargate batch jobs (NEW)
- [docs/ECS_MIGRATION_GUIDE.md](docs/ECS_MIGRATION_GUIDE.md) - Complete migration guide
- [docs/deployment.md](docs/deployment.md) - EC2 web app deployment
- [docs/ci-cd-setup.md](docs/ci-cd-setup.md) - CI/CD pipeline details

### Production Considerations

1. **Database:**
   - Use managed PostgreSQL (e.g., AWS RDS, Google Cloud SQL)
   - Enable connection pooling via SQLAlchemy
   - Regular backups and point-in-time recovery

2. **Environment Variables:**
   ```bash
   DATABASE_URL=postgresql://user:pass@host:5432/db
   REDDIT_CLIENT_ID=production_client_id
   REDDIT_CLIENT_SECRET=production_secret
   ```

3. **Scaling:**
   - Run sentiment analysis as async background jobs
   - Use Redis for caching frequent queries
   - Deploy multiple API instances behind load balancer

4. **Monitoring:**
   - Health check endpoint for uptime monitoring
   - Structured logging for error tracking
   - Performance metrics collection

### Docker Deployment

```bash
# Build and run with Docker Compose
docker compose up -d

# View logs
docker compose logs -f api

# Scale API instances
docker compose up -d --scale api=3
```

---

## 🛠️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://test:test@localhost:5432/test` |
| `REDDIT_CLIENT_ID` | Reddit API client ID | Required for Reddit scraping |
| `REDDIT_CLIENT_SECRET` | Reddit API secret | Required for Reddit scraping |
| `REDDIT_USER_AGENT` | Reddit API user agent | `MarketPulse/1.0 by MarketPulseBot` |
| `FINNHUB_SECRET` | Finnhub API key (optional) | None |

### Sentiment Configuration

Customize sentiment analysis in [config.py](app/config.py):

```python
sentiment_use_llm: bool = True              # Enable FinBERT
sentiment_llm_model: str = "ProsusAI/finbert"
sentiment_use_gpu: bool = False             # CPU inference
sentiment_fallback_vader: bool = True       # VADER fallback
sentiment_dual_model: bool = True           # Dual-model fusion
sentiment_strong_threshold: float = 0.2     # Strong sentiment threshold
```

---

## 📈 Performance

### Optimizations

- **Database Indexes**: Optimized for common query patterns
- **Batch Processing**: Efficient bulk operations for data ingestion
- **Connection Pooling**: Persistent database connections
- **Async I/O**: Non-blocking API endpoints
- **Incremental Processing**: Delta-based updates, not full refreshes

### Benchmarks

- **Sentiment Analysis**: ~50-100 articles/second (CPU)
- **Ticker Linking**: ~200 articles/second
- **API Response Time**: <100ms for cached queries
- **Reddit Scraping**: 500-1000 comments/minute (rate-limited)

---

## 🔍 Troubleshooting

### Common Issues

**Port Already in Use:**
```bash
make down          # Stop existing services
make up            # Restart
```

**Database Connection Error:**
```bash
make clean         # Clean everything
make up            # Restart services
make db-init       # Reinitialize database
make seed-tickers  # Reseed data
```

**Reddit API Rate Limit:**
- The scraper automatically handles rate limits with exponential backoff
- Use `--verbose` flag to see rate limit status
- Reduce `--max-threads` if hitting limits frequently

**Sentiment Analysis Slow:**
- FinBERT runs on CPU by default (set `sentiment_use_gpu=True` for GPU)
- Process in smaller batches with `--batch-size` flag
- Use VADER-only mode for faster (but less accurate) results

---

## 🔒 Security

All sensitive credentials are managed through environment variables and **never** committed to the repository. The `.env` file is gitignored and contains all API keys and secrets.

**Required API Keys:**
- Reddit API credentials (get from https://www.reddit.com/prefs/apps)
- PostgreSQL password
- Optional: Finnhub API key

For detailed security information, see [SECURITY_ASSESSMENT.md](SECURITY_ASSESSMENT.md) (private file, not in repo).

---

## 📋 Recent Changes

### Latest Updates (October 2025)

**Features:**
- Added scraping status tracking table for monitoring Reddit data collection
- Improved sentiment analytics service with better distribution metrics
- Enhanced UI with better base template and responsive design
- Production deployment to EC2 with automated CI/CD pipeline

**Infrastructure:**
- Deployed to AWS EC2 at alexstocks.com
- Automated CI/CD via GitHub Actions (test → lint → security → deploy)
- Nginx reverse proxy with SSL/HTTPS via Let's Encrypt
- Systemd service for application management
- Cron jobs for automated hourly data collection

**Performance:**
- Reddit scraping with intelligent rate limiting and retry logic
- Stock price collection every 15 minutes during market hours
- Historical data collection daily at 2 PM PT
- Efficient database queries with proper indexing

**Security:**
- All secrets managed via environment variables
- GitHub Actions deployment using SSH keys from GitHub Secrets
- EC2 security groups properly configured
- SSL certificate auto-renewal

---

## 📚 Documentation

Detailed documentation available in the [docs/](docs/) directory:

- [Implementation Status](docs/IMPLEMENTATION_STATUS.md) - Feature completion tracker
- [Reddit Setup Guide](docs/REDDIT_SETUP.md) - Reddit API configuration
- [Testing Guide](docs/TESTING.md) - Test suite documentation
- [LLM Sentiment Setup](docs/LLM_SENTIMENT_SETUP.md) - FinBERT configuration
- [Ticker Linking](docs/TICKER_LINKING_IMPROVEMENTS.md) - Linking algorithm details
- [Cron Jobs](docs/CRON_JOBS_SUMMARY.md) - Automated data pipeline
- [Deployment Guide](docs/deployment.md) - EC2 deployment instructions
- [CI/CD Setup](docs/ci-cd-setup.md) - GitHub Actions pipeline

---

## 🤝 Contributing

### Development Workflow

1. **Fork & Clone**: Fork the repository and clone locally
2. **Install Dependencies**: Run `uv sync` to install all dependencies
3. **Create Branch**: Create a feature branch from `main`
4. **Make Changes**: Implement your feature with tests
5. **Run Tests**: Ensure all tests pass with `make test`
6. **Format Code**: Run `make format` to format code
7. **Submit PR**: Open a pull request with clear description

### Code Standards

- **Type Hints**: All functions must have type annotations
- **Docstrings**: Public functions require docstrings
- **Testing**: New features require unit tests
- **Linting**: Code must pass `make lint` checks
- **Formatting**: Use Black (88 char line length)

---

## 📝 License

This project is available for personal and educational use.

---

## 🙏 Acknowledgments

- **FinBERT** by ProsusAI for financial sentiment analysis
- **VADER** sentiment analysis library
- **PRAW** for Reddit API integration
- **FastAPI** framework and community
- **yfinance** for stock market data

---

## 📬 Support

For issues, questions, or contributions:
- **Security Issues**: Please report security vulnerabilities privately
- **Bug Reports**: [GitHub Issues](https://github.com/your-repo/market-pulse/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-repo/market-pulse/discussions)

---

## 📝 License

This project is available for personal and educational use. Not for commercial redistribution.

---

**Built with ❤️ for market analytics enthusiasts**
