#!/bin/bash

# Market Pulse Cron Jobs Cleanup Script
# =====================================
# 
# This script removes old cron job configurations
# and prepares for the new 15-minute pipeline

set -e

echo "🧹 Cleaning up old Market Pulse cron jobs..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Backup current crontab
print_status "Backing up current crontab..."
crontab -l > /Users/alex/logs/market-pulse/crontab-backup-$(date +%Y%m%d-%H%M%S).txt 2>/dev/null || true
print_success "Crontab backed up"

# Show current crontab
print_status "Current crontab:"
crontab -l 2>/dev/null || echo "No crontab found"

echo ""
print_warning "This will remove ALL existing cron jobs and replace them with the new 15-minute pipeline"
echo ""

read -p "Are you sure you want to continue? (y/N): " confirm

if [[ $confirm != [yY] && $confirm != [yY][eE][sS] ]]; then
    print_status "Cleanup cancelled"
    exit 0
fi

# Remove all existing cron jobs
print_status "Removing all existing cron jobs..."
crontab -r 2>/dev/null || true
print_success "All cron jobs removed"

# Show empty crontab
print_status "Current crontab (should be empty):"
crontab -l 2>/dev/null || echo "No crontab found (this is expected)"

echo ""
print_success "Cleanup completed!"
print_status "You can now run ./setup-cron-15min.sh to install the new 15-minute pipeline"
