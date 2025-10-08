.PHONY: help up down db-init seed-tickers add-sentiment ingest-hour ingest-24h reddit-ingest reddit-wsb reddit-stocks reddit-investing add-reddit-columns add-reddit-thread-table reddit-incremental reddit-status collect-stock-prices collect-historical-data collect-both-stock-data test clean

help: ## Show this help message
	@echo "Market Pulse - Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start postgres and api services
	docker compose up -d postgres
	@echo "Waiting for postgres to be ready..."
	@sleep 5
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

down: ## Stop all services
	docker compose down

db-init: ## Initialize database schema
	uv run python -m app.scripts.init_db

seed-tickers: ## Seed ticker data
	uv run python -m app.scripts.seed_tickers

seed-sample-data: ## Seed sample articles for demonstration
	uv run python -m app.scripts.seed_sample_articles

query-db: ## Query database (use --help for options)
	uv run python -m app.scripts.query_db

clean-sample: ## Clean up sample and test data
	uv run python -m app.scripts.clean_sample_data


add-sentiment: ## Add sentiment column to article table
	uv run python -m app.scripts.add_sentiment_column

add-reddit-columns: ## Add Reddit-specific columns to article table
	uv run python -m app.scripts.add_reddit_columns

add-reddit-thread-table: ## Add RedditThread table for tracking scraping progress
	uv run python -m app.scripts.add_reddit_thread_table

# Production Reddit Scraper (unified, comprehensive)
# NOTE: Legacy targets (reddit-ingest, reddit-wsb, reddit-stocks, reddit-investing)
# have been removed. They used the deprecated ingest/reddit.py general post scraper.
# Use the production scraper below for discussion thread scraping.
reddit-scrape-incremental: ## Production incremental scraper (for 15-min cron)
	uv run python -m ingest.reddit_scraper_cli --mode incremental

reddit-scrape-backfill: ## Production backfill scraper (requires START and END dates)
	@if [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "❌ Error: START and END dates required"; \
		echo "Usage: make reddit-scrape-backfill START=2025-09-01 END=2025-09-30"; \
		exit 1; \
	fi
	uv run python -m ingest.reddit_scraper_cli --mode backfill --start $(START) --end $(END)

reddit-scrape-status: ## Show production scraper status
	uv run python -m ingest.reddit_scraper_cli --mode status

# Sentiment Analysis Jobs (LLM by default)
analyze-sentiment: ## Run sentiment analysis on articles without sentiment
	uv run python app/jobs/analyze_sentiment.py

analyze-sentiment-reddit: ## Run sentiment analysis on Reddit articles only
	uv run python app/jobs/analyze_sentiment.py --source reddit

analyze-sentiment-recent: ## Run sentiment analysis on articles from last 24 hours
	uv run python app/jobs/analyze_sentiment.py --hours-back 24

# LLM Sentiment Override Jobs
override-sentiment-llm: ## Override all existing sentiment with LLM sentiment
	uv run python app/jobs/override_sentiment_with_llm.py

override-sentiment-llm-reddit: ## Override Reddit sentiment with LLM sentiment
	uv run python app/jobs/override_sentiment_with_llm.py --source reddit

override-sentiment-llm-force: ## Force override ALL articles with LLM sentiment
	uv run python app/jobs/override_sentiment_with_llm.py --force-all

# Dual Model Sentiment Override Jobs
override-sentiment-dual: ## Override all existing sentiment with dual model approach (LLM + VADER)
	uv run python app/jobs/override_sentiment_dual_model.py

override-sentiment-dual-reddit: ## Override Reddit sentiment with dual model approach
	uv run python app/jobs/override_sentiment_dual_model.py --source reddit

override-sentiment-dual-force: ## Force override ALL articles with dual model approach
	uv run python app/jobs/override_sentiment_dual_model.py --force-all

override-sentiment-dual-recent: ## Override sentiment for articles from last 24 hours with dual model
	uv run python app/jobs/override_sentiment_dual_model.py --hours-back 24

# Stock Price Collection Jobs
collect-stock-prices: ## Collect current stock prices for all tickers
	uv run python app/scripts/collect_all_stock_data.py --type current

collect-historical-data: ## Collect historical stock price data (1 month)
	uv run python app/scripts/collect_all_stock_data.py --type historical --period 1mo

collect-both-stock-data: ## Collect both current and historical stock data
	uv run python app/scripts/collect_all_stock_data.py --type both --period 1mo

test-stock-collection: ## Test stock data collection with 3 sample tickers
	uv run python app/scripts/test_stock_collection.py

setup-stock-cron: ## Setup cron job to collect stock prices every 15 minutes
	./scripts/setup-stock-price-cron.sh

test-stock: ## Run stock-related tests
	uv run pytest tests/test_stock*.py -v

# Smart Stock Collection (filters inactive tickers for faster collection)
collect-stock-prices-smart: ## Collect current prices (SMART - excludes warrants/units/rights)
	uv run python app/scripts/collect_stock_data_smart.py --type current

collect-stock-prices-test: ## Test collection with first 10 tickers
	uv run python app/scripts/collect_stock_data_smart.py --type current --limit 10

analyze-tickers: ## Analyze ticker database and show statistics
	uv run python app/scripts/filter_active_tickers.py

check-rate-limit: ## Check if Yahoo Finance rate limit has cleared
	uv run python app/scripts/check_rate_limit.py

# Combined Jobs (Scraping + Sentiment)
scrape-and-analyze-posts: ## Scrape Reddit posts and analyze sentiment
	uv run python app/jobs/scrape_and_analyze.py posts

scrape-and-analyze-comments: ## Scrape Reddit comments and analyze sentiment
	uv run python app/jobs/scrape_and_analyze.py comments

scrape-and-analyze-full: ## FULL scrape latest daily thread + sentiment analysis
	make reddit-full-scrape-latest && make analyze-sentiment-recent

test: ## Run all tests
	uv run pytest tests/ -v

test-unit: ## Run unit tests only
	uv run pytest tests/ -v -m "not integration and not performance"

test-integration: ## Run integration tests only
	uv run pytest tests/ -v -m "integration"

test-real-world: ## Run real-world integration tests (requires database with data)
	uv run pytest tests/test_real_world_integration.py -v --tb=short

test-performance: ## Run performance tests only
	uv run pytest tests/ -v -m "performance"

test-reddit: ## Run Reddit-related tests
	uv run pytest tests/ -v -k "reddit"

test-sentiment: ## Run sentiment analysis tests
	uv run pytest tests/ -v -k "sentiment"

test-linking: ## Run ticker linking tests
	uv run pytest tests/ -v -k "linking"

test-coverage: ## Run tests with coverage report
	uv run pytest tests/ -v --cov=app --cov=ingest --cov-report=html --cov-report=term

test-fast: ## Run fast tests only (exclude slow tests)
	uv run pytest tests/ -v -m "not slow"

lint: ## Run linting
	uv run ruff check .
	uv run black --check .
	uv run mypy .

lint-fix: ## Run linting and fix issues
	uv run ruff check --fix .
	uv run black .

format: ## Format code
	uv run black .
	uv run ruff check --fix .

security: ## Run security checks
	uv run bandit -r app/ ingest/ -f json -o bandit-report.json || true

clean: ## Clean up containers and volumes
	docker compose down -v
	docker system prune -f

# ============================================================================
# ECS Fargate Deployment Commands
# ============================================================================

# Docker/ECR Commands
ecr-login: ## Login to AWS ECR
	aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $(shell aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com

build-jobs-image: ## Build jobs Docker image locally
	docker build -f jobs/Dockerfile -t market-pulse-jobs:local .

push-jobs-image: ecr-login ## Build and push jobs image to ECR
	$(eval ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text))
	docker build -f jobs/Dockerfile --platform linux/amd64 -t $(ACCOUNT_ID).dkr.ecr.us-east-1.amazonaws.com/market-pulse-jobs:latest .
	docker push $(ACCOUNT_ID).dkr.ecr.us-east-1.amazonaws.com/market-pulse-jobs:latest
	@echo "✅ Pushed image to ECR"

# Terraform Commands
tf-init: ## Initialize Terraform
	cd infrastructure/terraform && terraform init

tf-plan: ## Plan Terraform changes
	cd infrastructure/terraform && terraform plan

tf-apply: ## Apply Terraform changes
	cd infrastructure/terraform && terraform apply

tf-destroy: ## Destroy Terraform resources (BE CAREFUL!)
	cd infrastructure/terraform && terraform destroy

# ECS Task Management
ecs-run-scraper: ## Manually trigger Reddit scraper task
	$(eval CLUSTER := market-pulse-jobs)
	$(eval TASK_DEF := market-pulse-reddit-scraper)
	$(eval SUBNETS := $(shell cd infrastructure/terraform && terraform output -json private_subnet_ids 2>/dev/null | jq -r 'join(",")' || echo "subnet-0cd442445909a114c,subnet-0be6093ab7853be0c"))
	$(eval SG := $(shell aws ec2 describe-security-groups --filters "Name=group-name,Values=market-pulse-ecs-tasks" --query 'SecurityGroups[0].GroupId' --output text))
	aws ecs run-task \
		--cluster $(CLUSTER) \
		--task-definition $(TASK_DEF) \
		--network-configuration "awsvpcConfiguration={subnets=[$(SUBNETS)],securityGroups=[$(SG)],assignPublicIp=ENABLED}" \
		--capacity-provider-strategy capacityProvider=FARGATE_SPOT,weight=1

ecs-run-sentiment: ## Manually trigger sentiment analysis task
	$(eval CLUSTER := market-pulse-jobs)
	$(eval TASK_DEF := market-pulse-sentiment-analysis)
	$(eval SUBNETS := $(shell cd infrastructure/terraform && terraform output -json private_subnet_ids 2>/dev/null | jq -r 'join(",")' || echo "subnet-0cd442445909a114c,subnet-0be6093ab7853be0c"))
	$(eval SG := $(shell aws ec2 describe-security-groups --filters "Name=group-name,Values=market-pulse-ecs-tasks" --query 'SecurityGroups[0].GroupId' --output text))
	aws ecs run-task \
		--cluster $(CLUSTER) \
		--task-definition $(TASK_DEF) \
		--network-configuration "awsvpcConfiguration={subnets=[$(SUBNETS)],securityGroups=[$(SG)],assignPublicIp=ENABLED}" \
		--capacity-provider-strategy capacityProvider=FARGATE_SPOT,weight=1

ecs-run-status: ## Manually trigger daily status check task
	$(eval CLUSTER := market-pulse-jobs)
	$(eval TASK_DEF := market-pulse-daily-status)
	$(eval SUBNETS := $(shell cd infrastructure/terraform && terraform output -json private_subnet_ids 2>/dev/null | jq -r 'join(",")' || echo "subnet-0cd442445909a114c,subnet-0be6093ab7853be0c"))
	$(eval SG := $(shell aws ec2 describe-security-groups --filters "Name=group-name,Values=market-pulse-ecs-tasks" --query 'SecurityGroups[0].GroupId' --output text))
	aws ecs run-task \
		--cluster $(CLUSTER) \
		--task-definition $(TASK_DEF) \
		--network-configuration "awsvpcConfiguration={subnets=[$(SUBNETS)],securityGroups=[$(SG)],assignPublicIp=ENABLED}" \
		--capacity-provider-strategy capacityProvider=FARGATE_SPOT,weight=1

ecs-list-tasks: ## List running ECS tasks
	aws ecs list-tasks --cluster market-pulse-jobs

ecs-logs-scraper: ## Tail logs for Reddit scraper
	aws logs tail /ecs/market-pulse-jobs/reddit-scraper --follow

ecs-logs-sentiment: ## Tail logs for sentiment analysis
	aws logs tail /ecs/market-pulse-jobs/sentiment-analysis --follow

ecs-logs-status: ## Tail logs for daily status
	aws logs tail /ecs/market-pulse-jobs/daily-status --follow

# EventBridge Schedule Management
schedule-enable-all: ## Enable all EventBridge schedules
	aws scheduler update-schedule --name market-pulse-reddit-scraper --state ENABLED
	aws scheduler update-schedule --name market-pulse-sentiment-analysis --state ENABLED
	aws scheduler update-schedule --name market-pulse-daily-status --state ENABLED
	@echo "✅ All schedules enabled"

schedule-disable-all: ## Disable all EventBridge schedules
	aws scheduler update-schedule --name market-pulse-reddit-scraper --state DISABLED
	aws scheduler update-schedule --name market-pulse-sentiment-analysis --state DISABLED
	aws scheduler update-schedule --name market-pulse-daily-status --state DISABLED
	@echo "⏸️  All schedules disabled"

schedule-status: ## Check status of all EventBridge schedules
	@echo "📋 Schedule Status:"
	@aws scheduler get-schedule --name market-pulse-reddit-scraper --query '[Name,State]' --output text
	@aws scheduler get-schedule --name market-pulse-sentiment-analysis --query '[Name,State]' --output text
	@aws scheduler get-schedule --name market-pulse-daily-status --query '[Name,State]' --output text
