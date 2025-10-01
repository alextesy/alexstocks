# Market Pulse

A lean MVP for market news analytics that tracks sentiment and momentum across tickers.

## Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker & Docker Compose

### Setup

1. **Clone and navigate to the project**
   ```bash
   cd market-pulse-v2
   ```

2. **Create environment file**
   ```bash
   cp env.example .env
   ```
   The default settings work for local development.

3. **Start the database**
   ```bash
   make up
   ```
   This starts PostgreSQL and the API server.

4. **Initialize the database**
   ```bash
   make db-init
   ```

5. **Seed ticker data**
   ```bash
   make seed-tickers
   ```

6. **Add sample articles (optional)**
   ```bash
   make seed-sample-data
   ```

### Access the App

- **Web Interface**: http://localhost:8000/
- **Health Check**: http://localhost:8000/health
- **Ticker Pages**: http://localhost:8000/t/AAPL

## Available Commands

```bash
make help          # Show all available commands
make up            # Start postgres and api services
make down          # Stop all services
make db-init       # Initialize database schema
make seed-tickers     # Seed ticker data
make seed-sample-data # Seed sample articles for demo
make test             # Run tests
make lint          # Run linting
make format        # Format code
make clean         # Clean up containers and volumes
```

## Troubleshooting

### Port Already in Use
If you get "Address already in use" error:
```bash
make down          # Stop existing services
make up            # Restart
```

### Database Issues
```bash
make clean         # Clean everything and start fresh
make up
make db-init
make seed-tickers
```

## Project Structure

```
app/
├── main.py           # FastAPI application
├── config.py         # Configuration management
├── db/               # Database models and session
├── scripts/          # Database setup scripts
├── services/         # Business logic
└── templates/        # HTML templates

data/
└── tickers_core.csv  # Ticker data

ingest/               # Data ingestion modules
tests/                # Test files
```

## Development

The app uses:
- **FastAPI** for the web API
- **SQLAlchemy** for database ORM
- **PostgreSQL** for data storage
- **Tailwind CSS** for styling
- **uv** for Python package management

## Next Steps

- Implement sentiment analysis
- Add real-time data to the web interface
- Add additional data sources beyond Reddit
