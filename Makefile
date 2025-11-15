.PHONY: help up down db-init seed-tickers add-sentiment ingest-hour ingest-24h reddit-ingest reddit-wsb reddit-stocks reddit-investing add-reddit-columns add-reddit-thread-table reddit-incremental reddit-status collect-stock-prices collect-historical-data collect-both-stock-data test clean

help: ## Show this help message
	@echo "AlexStocks - Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

redis-up: ## Start Redis (Docker, 200MB, LRU)
	@if docker ps -a --format '{{.Names}}' | grep -w redis >/dev/null 2>&1; then \
		echo "➡️  Redis container exists. Starting..."; \
		docker start redis >/dev/null; \
	else \
		echo "➡️  Creating Redis container..."; \
		docker run -d --name redis -p 6379:6379 redis:7-alpine \
		  redis-server --maxmemory 200mb --maxmemory-policy allkeys-lru --appendonly no >/dev/null; \
	fi; \
	 docker exec -it redis redis-cli ping || true

redis-down: ## Stop and remove Redis container
	- docker stop redis >/dev/null 2>&1 || true
	- docker rm redis >/dev/null 2>&1 || true
	@echo "🛑 Redis stopped and removed (if it existed)."

rate-limit-smoke: ## Hammer an endpoint to observe 429 with Retry-After, and test caps
	@echo "Note: Ensure the API is running on http://127.0.0.1:8000"
	@echo "\n➡️  Testing parameter caps (expect 422 or 400):"
	@echo "- /api/sentiment/time-series with excessive days"
	@curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000/api/sentiment/time-series?ticker=AAPL&days=9999"
	@echo "- /api/ticker/TSLA/articles with excessive limit"
	@curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000/api/ticker/TSLA/articles?page=1&limit=9999"
	@echo "\n➡️  Testing rate limiting (expect mix of 200 and 429):"
	@echo "Sending 80 requests to /api/mentions/hourly ..."
	@bash -c 'for i in $$(seq 1 80); do \
		curl -s -o /dev/null -w "%{http_code}\\n" "http://127.0.0.1:8000/api/mentions/hourly?tickers=AAPL&hours=1"; \
	done | sort | uniq -c'

up: ## Start postgres and api services
	docker compose up -d postgres
	@echo "Waiting for postgres to be ready..."
	@sleep 5
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

down: ## Stop all services
	docker compose down

db-init: ## Initialize database schema
	uv run python -m app.scripts.init_db

# Alembic Migration Commands
migrate-status: ## Show current migration status
	uv run alembic current

migrate-history: ## Show migration history
	uv run alembic history --verbose

migrate-up: ## Run all pending migrations
	uv run alembic upgrade head

migrate-down: ## Rollback last migration
	uv run alembic downgrade -1

migrate-create: ## Create new migration (NAME=description)
	@if [ -z "$(NAME)" ]; then \
		echo "❌ Error: NAME required"; \
		echo "Usage: make migrate-create NAME=add_new_column"; \
		exit 1; \
	fi
	uv run alembic revision --autogenerate -m "$(NAME)"

migrate-check: ## Check if migrations are needed (autogenerate dry-run)
	uv run alembic check

seed-tickers: ## Seed ticker data
	uv run python -m app.scripts.seed_tickers

seed-sample-data: ## Seed sample articles for demonstration
	uv run python -m app.scripts.seed_sample_articles

seed-users: ## Seed sample users (disabled in production)
	uv run python -m app.scripts.seed_users

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

# Production Reddit Scraper (Multi-Subreddit + Top Posts)
# Supports multiple subreddits via YAML config, scrapes both daily discussions and top posts
# Config: jobs/config/reddit_scraper_config.yaml

reddit-scrape-incremental: ## Production scraper - all enabled subreddits (discussions + top posts)
	cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode incremental

reddit-scrape-ecs: ## Production scraper (matches ECS task definition exactly)
	cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode incremental --config config/reddit_scraper_config.yaml

reddit-scrape-wsb: ## Scrape wallstreetbets only (discussions + top posts)
	cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode incremental --subreddit wallstreetbets

reddit-scrape-stocks: ## Scrape r/stocks only (discussions + top posts)
	cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode incremental --subreddit stocks

reddit-scrape-investing: ## Scrape r/investing only (discussions + top posts)
	cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode incremental --subreddit investing

reddit-scrape-custom-config: ## Scrape with custom config file (CONFIG=path/to/config.yaml)
	@if [ -z "$(CONFIG)" ]; then \
		echo "❌ Error: CONFIG path required"; \
		echo "Usage: make reddit-scrape-custom-config CONFIG=my_config.yaml"; \
		exit 1; \
	fi
	cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode incremental --config $(CONFIG)

reddit-scrape-backfill: ## Backfill historical data (requires SUBREDDIT, START, END)
	@if [ -z "$(SUBREDDIT)" ] || [ -z "$(START)" ] || [ -z "$(END)" ]; then \
		echo "❌ Error: SUBREDDIT, START and END dates required"; \
		echo "Usage: make reddit-scrape-backfill SUBREDDIT=wallstreetbets START=2025-09-01 END=2025-09-30"; \
		exit 1; \
	fi
	cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode backfill --subreddit $(SUBREDDIT) --start $(START) --end $(END)

reddit-scrape-status: ## Show scraping status for wallstreetbets
	cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode status

reddit-scrape-status-all: ## Show scraping status for specific subreddit (SUB=name)
	@if [ -z "$(SUB)" ]; then \
		cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode status; \
	else \
		cd jobs && PYTHONPATH=.. uv run python -m ingest.reddit_scraper_cli --mode status --subreddit $(SUB); \
	fi

# Sentiment Analysis Jobs (LLM by default)
analyze-sentiment: ## Run sentiment analysis on articles without sentiment
	cd jobs && PYTHONPATH=.. uv run python -m jobs.analyze_sentiment

analyze-sentiment-reddit: ## Run sentiment analysis on Reddit articles only
	cd jobs && PYTHONPATH=.. uv run python -m jobs.analyze_sentiment --source reddit

analyze-sentiment-recent: ## Run sentiment analysis on articles from last 24 hours
	cd jobs && PYTHONPATH=.. uv run python -m jobs.analyze_sentiment --hours-back 24

# LLM Sentiment Override Jobs
override-sentiment-llm: ## Override all existing sentiment with LLM sentiment
	cd jobs && PYTHONPATH=.. uv run python -m jobs.override_sentiment_with_llm

override-sentiment-llm-reddit: ## Override Reddit sentiment with LLM sentiment
	cd jobs && PYTHONPATH=.. uv run python -m jobs.override_sentiment_with_llm --source reddit

override-sentiment-llm-force: ## Force override ALL articles with LLM sentiment
	cd jobs && PYTHONPATH=.. uv run python -m jobs.override_sentiment_with_llm --force-all

# Dual Model Sentiment Override Jobs
override-sentiment-dual: ## Override all existing sentiment with dual model approach (LLM + VADER)
	cd jobs && PYTHONPATH=.. uv run python -m jobs.override_sentiment_dual_model

override-sentiment-dual-reddit: ## Override Reddit sentiment with dual model approach
	cd jobs && PYTHONPATH=.. uv run python -m jobs.override_sentiment_dual_model --source reddit

override-sentiment-dual-force: ## Force override ALL articles with dual model approach
	cd jobs && PYTHONPATH=.. uv run python -m jobs.override_sentiment_dual_model --force-all

override-sentiment-dual-recent: ## Override sentiment for articles from last 24 hours with dual model
	cd jobs && PYTHONPATH=.. uv run python -m jobs.override_sentiment_dual_model --hours-back 24

# Stock Price Collection Jobs
collect-stock-prices: ## Collect current stock prices for all tickers
	uv run python app/scripts/collect_all_stock_data.py --type current

collect-historical-data: ## Collect historical stock price data (1 month)
	uv run python app/scripts/collect_all_stock_data.py --type historical --period 1mo

collect-both-stock-data: ## Collect both current and historical stock data
	uv run python app/scripts/collect_all_stock_data.py --type both --period 1mo

test-stock-collection: ## Test stock data collection with 3 sample tickers
	uv run python app/scripts/test_stock_collection.py

collect-top50-prices: ## Collect stock prices for top 50 tickers (production job)
	cd jobs && PYTHONPATH=.. uv run python -m jobs.stock_price_collector

setup-stock-cron: ## Setup cron job to collect stock prices every 15 minutes
	./scripts/setup-stock-price-cron.sh

test-stock: ## Run stock-related tests
	uv run pytest tests/test_stock*.py -v

test-users: ## Run user repository tests
	uv run pytest tests/db/test_users.py -v

# Smart Stock Collection (filters inactive tickers for faster collection)
collect-stock-prices-smart: ## Collect current prices (SMART - excludes warrants/units/rights)
	uv run python app/scripts/collect_stock_data_smart.py --type current

collect-stock-prices-test: ## Test collection with first 10 tickers
	uv run python app/scripts/collect_stock_data_smart.py --type current --limit 10

analyze-tickers: ## Analyze ticker database and show statistics
	uv run python app/scripts/filter_active_tickers.py

check-rate-limit: ## Check if Yahoo Finance rate limit has cleared
	uv run python app/scripts/check_rate_limit.py

send-test-email: ## Send a test email to verify email service configuration
	uv run python app/scripts/send_test_email.py

send-daily-emails: ## Run the daily email dispatch job locally
	cd jobs && PYTHONPATH=.. uv run python -m jobs.jobs.send_daily_emails

send-daily-emails-dry-run: ## Run the daily email dispatch job in dry-run mode
	cd jobs && PYTHONPATH=.. uv run python -m jobs.jobs.send_daily_emails --dry-run

# Combined Jobs (Scraping + Sentiment)
scrape-and-analyze-posts: ## Scrape Reddit posts and analyze sentiment
	cd jobs && PYTHONPATH=.. uv run python -m jobs.scrape_and_analyze posts

scrape-and-analyze-comments: ## Scrape Reddit comments and analyze sentiment
	cd jobs && PYTHONPATH=.. uv run python -m jobs.scrape_and_analyze comments

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

push-jobs-image-test: ecr-login ## Build and push jobs image with test tag
	$(eval ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text))
	$(eval TAG := test-$(shell date +%Y%m%d-%H%M%S))
	docker build -f jobs/Dockerfile --platform linux/amd64 -t $(ACCOUNT_ID).dkr.ecr.us-east-1.amazonaws.com/market-pulse-jobs:$(TAG) .
	docker push $(ACCOUNT_ID).dkr.ecr.us-east-1.amazonaws.com/market-pulse-jobs:$(TAG)
	@echo "✅ Pushed image to ECR with tag: $(TAG)"
	@echo "$(TAG)" > /tmp/last-test-tag.txt

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

ecs-update-status-task: ## Update daily status task definition with new image (TAG=tag or latest)
	@if [ -z "$(TAG)" ]; then \
		echo "❌ Error: TAG required"; \
		echo "Usage: make ecs-update-status-task TAG=test-20250101-120000"; \
		echo "   or: make ecs-update-status-task TAG=latest"; \
		exit 1; \
	fi
	$(eval ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text))
	$(eval TASK_DEF := market-pulse-daily-status)
	$(eval IMAGE := $(ACCOUNT_ID).dkr.ecr.us-east-1.amazonaws.com/market-pulse-jobs:$(TAG))
	@echo "📦 Updating task definition $(TASK_DEF) with image $(IMAGE)..."
	@python3 -c "import json, sys, subprocess; \
		result = subprocess.run(['aws', 'ecs', 'describe-task-definition', '--task-definition', '$(TASK_DEF)', '--output', 'json'], \
			capture_output=True, text=True, check=True); \
		data = json.loads(result.stdout); \
		td = data['taskDefinition']; \
		td['containerDefinitions'][0]['image'] = '$(IMAGE)'; \
		td.pop('taskDefinitionArn', None); \
		td.pop('revision', None); \
		td.pop('status', None); \
		td.pop('requiresAttributes', None); \
		td.pop('compatibilities', None); \
		td.pop('registeredAt', None); \
		td.pop('registeredBy', None); \
		json.dump(td, sys.stdout)" > /tmp/task-def-new.json
	@aws ecs register-task-definition --cli-input-json file:///tmp/task-def-new.json --output json > /tmp/task-def-result.json || (echo "❌ Failed to register task definition"; exit 1)
		@python3 -c "import json; data=json.load(open('/tmp/task-def-result.json')); print(f\"✅ Task definition updated to revision {data['taskDefinition']['revision']}\")" || (echo "❌ Failed to read task definition result"; exit 1)
	@echo "Run with: make ecs-run-status"

ecs-update-status-and-run: push-jobs-image-test ## Build, push, update task definition, and run daily status job (all-in-one)
	$(eval TAG := $(shell cat /tmp/last-test-tag.txt 2>/dev/null || echo ""))
	@if [ -z "$(TAG)" ]; then \
		echo "❌ Error: Could not find test tag. Run 'make push-jobs-image-test' first."; \
		exit 1; \
	fi
	@echo "📦 Using tag: $(TAG)"
	$(MAKE) ecs-update-status-task TAG=$(TAG)
	@echo "🚀 Running task..."
	$(MAKE) ecs-run-status
	@echo "📋 To view logs: make ecs-logs-status"

ecs-run-stock-prices: ## Manually trigger stock price collector task
	$(eval CLUSTER := market-pulse-jobs)
	$(eval TASK_DEF := market-pulse-stock-price-collector)
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

ecs-logs-stock-prices: ## Tail logs for stock price collector
	aws logs tail /ecs/market-pulse-jobs/stock-price-collector --follow

ecs-run-send-emails: ## Manually trigger send daily emails task
	$(eval CLUSTER := market-pulse-jobs)
	$(eval TASK_DEF := market-pulse-send-daily-emails)
	$(eval SUBNETS := $(shell cd infrastructure/terraform && terraform output -json private_subnet_ids 2>/dev/null | jq -r 'join(",")' || echo "subnet-0cd442445909a114c,subnet-0be6093ab7853be0c"))
	$(eval SG := $(shell aws ec2 describe-security-groups --filters "Name=group-name,Values=market-pulse-ecs-tasks" --query 'SecurityGroups[0].GroupId' --output text))
	aws ecs run-task \
		--cluster $(CLUSTER) \
		--task-definition $(TASK_DEF) \
		--network-configuration "awsvpcConfiguration={subnets=[$(SUBNETS)],securityGroups=[$(SG)],assignPublicIp=ENABLED}" \
		--capacity-provider-strategy capacityProvider=FARGATE_SPOT,weight=1

ecs-logs-send-emails: ## Tail logs for send daily emails
	aws logs tail /ecs/market-pulse-jobs/send-daily-emails --follow

ecs-update-send-emails-task: ## Update send daily emails task definition with new image (TAG=tag or latest)
	@if [ -z "$(TAG)" ]; then \
		echo "❌ Error: TAG required"; \
		echo "Usage: make ecs-update-send-emails-task TAG=test-20250101-120000"; \
		echo "   or: make ecs-update-send-emails-task TAG=latest"; \
		exit 1; \
	fi
	$(eval ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text))
	$(eval TASK_DEF := market-pulse-send-daily-emails)
	$(eval IMAGE := $(ACCOUNT_ID).dkr.ecr.us-east-1.amazonaws.com/market-pulse-jobs:$(TAG))
	@echo "📦 Updating task definition $(TASK_DEF) with image $(IMAGE)..."
	@python3 -c "import json, sys, subprocess; \
		result = subprocess.run(['aws', 'ecs', 'describe-task-definition', '--task-definition', '$(TASK_DEF)', '--output', 'json'], \
			capture_output=True, text=True, check=True); \
		data = json.loads(result.stdout); \
		td = data['taskDefinition']; \
		td['containerDefinitions'][0]['image'] = '$(IMAGE)'; \
		td.pop('taskDefinitionArn', None); \
		td.pop('revision', None); \
		td.pop('status', None); \
		td.pop('requiresAttributes', None); \
		td.pop('compatibilities', None); \
		td.pop('registeredAt', None); \
		td.pop('registeredBy', None); \
		json.dump(td, sys.stdout)" > /tmp/task-def-new.json
	@aws ecs register-task-definition --cli-input-json file:///tmp/task-def-new.json --output json > /tmp/task-def-result.json || (echo "❌ Failed to register task definition"; exit 1)
	@python3 -c "import json; data=json.load(open('/tmp/task-def-result.json')); print(f\"✅ Task definition updated to revision {data['taskDefinition']['revision']}\")" || (echo "❌ Failed to read task definition result"; exit 1)
	@echo "Run with: make ecs-run-send-emails"

# EventBridge Schedule Management
schedule-enable-all: ## Enable all EventBridge schedules
	aws scheduler update-schedule --name market-pulse-reddit-scraper --state ENABLED
	aws scheduler update-schedule --name market-pulse-sentiment-analysis --state ENABLED
	aws scheduler update-schedule --name market-pulse-daily-status --state ENABLED
	aws scheduler update-schedule --name market-pulse-stock-price-collector --state ENABLED
	aws scheduler update-schedule --name market-pulse-send-daily-emails --state ENABLED
	@echo "✅ All schedules enabled"

schedule-disable-all: ## Disable all EventBridge schedules
	aws scheduler update-schedule --name market-pulse-reddit-scraper --state DISABLED
	aws scheduler update-schedule --name market-pulse-sentiment-analysis --state DISABLED
	aws scheduler update-schedule --name market-pulse-daily-status --state DISABLED
	aws scheduler update-schedule --name market-pulse-stock-price-collector --state DISABLED
	aws scheduler update-schedule --name market-pulse-send-daily-emails --state DISABLED
	@echo "⏸️  All schedules disabled"

schedule-status: ## Check status of all EventBridge schedules
	@echo "📋 Schedule Status:"
	@aws scheduler get-schedule --name market-pulse-reddit-scraper --query '[Name,State]' --output text
	@aws scheduler get-schedule --name market-pulse-sentiment-analysis --query '[Name,State]' --output text
	@aws scheduler get-schedule --name market-pulse-daily-status --query '[Name,State]' --output text
	@aws scheduler get-schedule --name market-pulse-stock-price-collector --query '[Name,State]' --output text
	@aws scheduler get-schedule --name market-pulse-send-daily-emails --query '[Name,State]' --output text

schedule-enable-stock-prices: ## Enable stock price collector schedule only
	aws scheduler update-schedule --name market-pulse-stock-price-collector --state ENABLED
	@echo "✅ Stock price collector schedule enabled"

schedule-disable-stock-prices: ## Disable stock price collector schedule only
	aws scheduler update-schedule --name market-pulse-stock-price-collector --state DISABLED
	@echo "⏸️  Stock price collector schedule disabled"

schedule-enable-send-emails: ## Enable send daily emails schedule only
	aws scheduler update-schedule --name market-pulse-send-daily-emails --state ENABLED
	@echo "✅ Send daily emails schedule enabled"

schedule-disable-send-emails: ## Disable send daily emails schedule only
	aws scheduler update-schedule --name market-pulse-send-daily-emails --state DISABLED
	@echo "⏸️  Send daily emails schedule disabled"
