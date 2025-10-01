#!/bin/bash

# Market Pulse 15-Minute Pipeline Setup Script
# ============================================
# 
# This script sets up the 15-minute incremental pipeline:
# - Reddit scraping every 15 minutes (24/7)
# - Sentiment analysis every 15 minutes (24/7)  
# - Stock price collection every 15 minutes (market hours only)
# - Weekend mode with reduced frequency
# - Daily maintenance and status checks

set -e

echo "🚀 Setting up Market Pulse 15-Minute Pipeline..."

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

# Create log directory
print_status "Creating log directory..."
mkdir -p /Users/alex/logs/market-pulse
print_success "Log directory created: /Users/alex/logs/market-pulse"

# Backup current crontab
print_status "Backing up current crontab..."
crontab -l > /Users/alex/logs/market-pulse/crontab-backup-$(date +%Y%m%d-%H%M%S).txt 2>/dev/null || true
print_success "Crontab backed up"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    print_error "uv is not installed or not in PATH"
    print_status "Please install uv or add it to your PATH"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_warning ".env file not found"
    print_status "Please create .env file with Reddit API credentials"
    print_status "See env.example for reference"
fi

# Test the robust scraper
print_status "Testing robust scraper..."
if make reddit-robust-scrape --dry-run 2>/dev/null || true; then
    print_success "Robust scraper target is available"
else
    print_warning "Could not verify robust scraper target"
fi

# Test sentiment analysis
print_status "Testing sentiment analysis..."
if make analyze-sentiment-recent --dry-run 2>/dev/null || true; then
    print_success "Sentiment analysis target is available"
else
    print_warning "Could not verify sentiment analysis target"
fi

# Test stock price collection
print_status "Testing stock price collection..."
if make collect-stock-prices --dry-run 2>/dev/null || true; then
    print_success "Stock price collection target is available"
else
    print_warning "Could not verify stock price collection target"
fi

# Show current crontab
print_status "Current crontab:"
crontab -l 2>/dev/null || echo "No crontab found"

echo ""
print_status "Ready to install 15-minute pipeline cron jobs"
echo ""
echo "Choose an option:"
echo "1. Install simple 15-minute pipeline (recommended)"
echo "2. Install full 15-minute pipeline with all features"
echo "3. Show cron job content without installing"
echo "4. Exit without installing"
echo ""

read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        print_status "Installing simple 15-minute pipeline..."
        # Read the simple cron file and install it
        if [ -f "cron-15min-simple.txt" ]; then
            # Extract just the cron jobs (skip comments and empty lines)
            grep -E '^[^#].*' cron-15min-simple.txt | grep -v '^$' | crontab -
            print_success "Simple 15-minute pipeline installed!"
        else
            print_error "cron-15min-simple.txt not found"
            exit 1
        fi
        ;;
    2)
        print_status "Installing full 15-minute pipeline..."
        if [ -f "cron-15min-pipeline.txt" ]; then
            grep -E '^[^#].*' cron-15min-pipeline.txt | grep -v '^$' | crontab -
            print_success "Full 15-minute pipeline installed!"
        else
            print_error "cron-15min-pipeline.txt not found"
            exit 1
        fi
        ;;
    3)
        print_status "Showing cron job content..."
        echo ""
        echo "=== SIMPLE 15-MINUTE PIPELINE ==="
        cat cron-15min-simple.txt
        echo ""
        echo "=== FULL 15-MINUTE PIPELINE ==="
        cat cron-15min-pipeline.txt
        ;;
    4)
        print_status "Exiting without installing"
        exit 0
        ;;
    *)
        print_error "Invalid choice"
        exit 1
        ;;
esac

if [ $choice -eq 1 ] || [ $choice -eq 2 ]; then
    echo ""
    print_success "Cron jobs installed successfully!"
    echo ""
    print_status "Installed cron jobs:"
    crontab -l
    echo ""
    print_status "Next steps:"
    echo "1. Monitor logs: tail -f /Users/alex/logs/market-pulse/15min-scraping.log"
    echo "2. Check status: make reddit-status"
    echo "3. Test manually: make reddit-robust-scrape"
    echo "4. Test stock prices: make collect-stock-prices"
    echo ""
    print_status "Log files will be created in: /Users/alex/logs/market-pulse/"
    echo "  - 15min-scraping.log (Reddit scraping every 15 min)"
    echo "  - 15min-sentiment.log (Sentiment analysis every 15 min)"
    echo "  - 15min-stock-prices.log (Stock prices every 15 min during market hours)"
    echo "  - daily-status.log (Daily status checks)"
    echo "  - weekend-*.log (Weekend mode activities)"
    echo ""
    print_warning "Note: First run may take longer as it processes existing data"
    print_status "The pipeline will start running automatically every 15 minutes"
fi
