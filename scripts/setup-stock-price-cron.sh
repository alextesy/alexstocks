#!/bin/bash
# Setup cron job for stock price collection every 15 minutes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Setting up stock price collection cron job..."
echo "Project directory: $PROJECT_DIR"

# Create cron job definition
CRON_JOB="*/15 * * * * cd $PROJECT_DIR && /usr/bin/env uv run python app/scripts/collect_all_stock_data.py --type current >> /tmp/stock_price_collection.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "collect_all_stock_data.py"; then
    echo "Cron job already exists. Updating..."
    # Remove old job
    crontab -l 2>/dev/null | grep -v "collect_all_stock_data.py" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "✓ Cron job installed successfully!"
echo ""
echo "Cron schedule: Every 15 minutes"
echo "Log file: /tmp/stock_price_collection.log"
echo ""
echo "To view current cron jobs:"
echo "  crontab -l"
echo ""
echo "To view logs:"
echo "  tail -f /tmp/stock_price_collection.log"
echo ""
echo "To remove this cron job:"
echo "  crontab -l | grep -v 'collect_all_stock_data.py' | crontab -"
