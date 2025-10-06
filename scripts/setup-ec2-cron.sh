#!/bin/bash

# EC2 Production Cron Setup Script
# =================================
#
# This script sets up production cron jobs on the EC2 server.
# It installs the cron-ec2-production.txt configuration.

set -e

echo "🚀 Setting up Market Pulse EC2 Production Cron Jobs..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "Makefile" ]; then
    print_error "Please run this script from the market-pulse-v2 directory"
    exit 1
fi

# Check if cron file exists
if [ ! -f "cron-ec2-production.txt" ]; then
    print_error "cron-ec2-production.txt not found"
    exit 1
fi

# Create log directory
print_status "Creating log directory..."
sudo mkdir -p /var/log/market-pulse
sudo chown ubuntu:ubuntu /var/log/market-pulse
print_success "Log directory created: /var/log/market-pulse"

# Backup current crontab
print_status "Backing up current crontab..."
crontab -l > /tmp/crontab-backup-$(date +%Y%m%d-%H%M%S).txt 2>/dev/null || true
print_success "Crontab backed up to /tmp"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    print_error "uv is not installed or not in PATH"
    print_status "Please install uv or add it to your PATH"
    exit 1
fi

# Check uv location
UV_PATH=$(which uv)
print_status "Found uv at: $UV_PATH"

# Test make targets
print_status "Testing make targets..."
if make --dry-run reddit-scrape-incremental &> /dev/null; then
    print_success "reddit-scrape-incremental target is available"
else
    print_warning "Could not verify reddit-scrape-incremental target"
fi

if make --dry-run analyze-sentiment-reddit &> /dev/null; then
    print_success "analyze-sentiment-reddit target is available"
else
    print_warning "Could not verify analyze-sentiment-reddit target"
fi

if make --dry-run collect-stock-prices-smart &> /dev/null; then
    print_success "collect-stock-prices-smart target is available"
else
    print_warning "Could not verify collect-stock-prices-smart target"
fi

# Show current crontab
echo ""
print_status "Current crontab:"
crontab -l 2>/dev/null || echo "No crontab found"

echo ""
print_status "Ready to install EC2 production cron jobs"
echo ""
echo "This will install the following jobs:"
echo "  - Reddit scraping: Every 15 minutes"
echo "  - Sentiment analysis: Every 15 minutes"
echo "  - Stock prices: Every 15 minutes (market hours)"
echo "  - Historical data: Daily at 2 PM PT"
echo "  - Weekend stock prices: Hourly"
echo "  - Daily status check: 4 AM UTC"
echo ""
read -p "Do you want to proceed? (y/n): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_status "Installation cancelled"
    exit 0
fi

print_status "Installing EC2 production cron jobs..."
crontab cron-ec2-production.txt
print_success "Cron jobs installed successfully!"

echo ""
print_status "Installed cron jobs:"
crontab -l
echo ""

print_success "✅ Setup complete!"
echo ""
print_status "Next steps:"
echo "1. Monitor Reddit scraping: tail -f /var/log/market-pulse/reddit-scraping.log"
echo "2. Monitor sentiment analysis: tail -f /var/log/market-pulse/sentiment-analysis.log"
echo "3. Monitor stock prices: tail -f /var/log/market-pulse/stock-prices.log"
echo "4. Check status: make reddit-scrape-status"
echo ""
print_status "Log files location: /var/log/market-pulse/"
echo "  - reddit-scraping.log (every 15 min)"
echo "  - sentiment-analysis.log (every 15 min)"
echo "  - stock-prices.log (every 15 min during market hours)"
echo "  - historical-data.log (daily at 2 PM PT)"
echo "  - stock-prices-weekend.log (hourly on weekends)"
echo "  - daily-status.log (daily at 4 AM UTC)"
echo ""
print_warning "Note: First run may take longer as it processes existing data"
print_status "Jobs will start running automatically according to their schedules"
echo ""
print_status "To view cron jobs: crontab -l"
print_status "To edit cron jobs: crontab -e"
print_status "To remove all cron jobs: crontab -r"
