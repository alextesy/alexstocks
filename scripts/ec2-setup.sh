#!/bin/bash
set -e

echo "🚀 Market Pulse EC2 Setup Script"
echo "================================"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Ubuntu
if [ ! -f /etc/lsb-release ]; then
    echo -e "${RED}❌ This script is designed for Ubuntu${NC}"
    exit 1
fi

# Get project directory
PROJECT_DIR="/opt/market-pulse-v2"

if [ ! -d "$PROJECT_DIR" ]; then
    echo -e "${RED}❌ Project directory not found: $PROJECT_DIR${NC}"
    echo "Please clone the repository first or adjust PROJECT_DIR"
    exit 1
fi

cd "$PROJECT_DIR"

# 1. Check environment variables
echo -e "\n${YELLOW}📋 Step 1: Checking environment variables${NC}"
if [ ! -f .env ]; then
    echo -e "${RED}⚠️  No .env file found${NC}"
    echo "Creating template .env file..."
    cat > .env << 'EOF'
POSTGRES_PASSWORD=marinA@1968
EOF
    echo -e "${YELLOW}⚠️  Please edit .env file with your actual values${NC}"
    echo "nano .env"
    exit 1
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# 2. Create log directory
echo -e "\n${YELLOW}📁 Step 2: Creating log directory${NC}"
sudo mkdir -p /var/log/market-pulse
sudo chown ubuntu:ubuntu /var/log/market-pulse
echo -e "${GREEN}✅ Log directory created${NC}"

# 3. Start PostgreSQL
echo -e "\n${YELLOW}🐘 Step 3: Starting PostgreSQL${NC}"
docker compose up -d postgres
echo "Waiting for PostgreSQL to be ready..."
sleep 10
echo -e "${GREEN}✅ PostgreSQL started${NC}"

# 4. Restore database dump (if exists)
DUMP_FILE="$HOME/market_pulse_dump.custom"
if [ -f "$DUMP_FILE" ]; then
    echo -e "\n${YELLOW}💾 Step 4: Restoring database dump${NC}"
    docker compose exec -T postgres pg_restore -U postgres -d market_pulse -v < "$DUMP_FILE"
    echo -e "${GREEN}✅ Database restored from dump${NC}"
else
    echo -e "\n${YELLOW}⚠️  No database dump found at $DUMP_FILE${NC}"
    echo "Initializing empty database..."
    uv run python -m app.scripts.init_db
    echo -e "${GREEN}✅ Database initialized${NC}"
fi

# 5. Set up systemd service
echo -e "\n${YELLOW}⚙️  Step 5: Creating systemd service${NC}"

# Detect uv location
UV_PATH=$(which uv 2>/dev/null || echo "/home/ubuntu/.local/bin/uv")
echo "Using uv at: $UV_PATH"

sudo tee /etc/systemd/system/market-pulse.service > /dev/null << EOF
[Unit]
Description=Market Pulse API
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$PROJECT_DIR
Environment="PATH=/home/ubuntu/.local/bin:/home/ubuntu/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$PROJECT_DIR/.env
ExecStartPre=/usr/bin/docker compose up -d postgres
ExecStartPre=/bin/sleep 5
ExecStart=$UV_PATH run uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable market-pulse
echo -e "${GREEN}✅ Systemd service created${NC}"

# 6. Set up cron jobs
echo -e "\n${YELLOW}⏰ Step 6: Setting up cron jobs${NC}"
CRON_FILE="/tmp/market-pulse-cron"
cat > "$CRON_FILE" << EOF
# Market Pulse Jobs
PATH=/home/ubuntu/.local/bin:/home/ubuntu/.cargo/bin:/usr/local/bin:/usr/bin:/bin

# Reddit scraping + sentiment
13 * * * * cd $PROJECT_DIR && $UV_PATH run python app/jobs/scrape_and_analyze.py comments >> /var/log/market-pulse/hourly.log 2>&1

# Stock prices every 15min during market hours (6:30 AM - 1:00 PM PT)
*/15 6-13 * * 1-5 cd $PROJECT_DIR && $UV_PATH run python app/scripts/collect_stock_data_smart.py --type current >> /var/log/market-pulse/stock-prices.log 2>&1

# Historical data once daily at 2:00 PM PT
0 14 * * 1-5 cd $PROJECT_DIR && $UV_PATH run python app/scripts/collect_stock_data_smart.py --type historical --period 1mo >> /var/log/market-pulse/historical-data.log 2>&1

# Weekend collection (reduced frequency)
0 * * * 0,6 cd $PROJECT_DIR && $UV_PATH run python app/scripts/collect_stock_data_smart.py --type current >> /var/log/market-pulse/stock-prices-weekend.log 2>&1
EOF

crontab "$CRON_FILE"
rm "$CRON_FILE"
echo -e "${GREEN}✅ Cron jobs installed${NC}"

# 7. Start the service
echo -e "\n${YELLOW}🚀 Step 7: Starting Market Pulse service${NC}"
sudo systemctl start market-pulse
sleep 3

# Check service status
if sudo systemctl is-active --quiet market-pulse; then
    echo -e "${GREEN}✅ Market Pulse service is running!${NC}"
else
    echo -e "${RED}❌ Service failed to start. Check logs:${NC}"
    echo "sudo journalctl -u market-pulse -n 50"
    exit 1
fi

# Summary
echo -e "\n${GREEN}================================${NC}"
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "Service status: sudo systemctl status market-pulse"
echo "View logs:      sudo journalctl -u market-pulse -f"
echo "Stop service:   sudo systemctl stop market-pulse"
echo "Restart:        sudo systemctl restart market-pulse"
echo ""
echo "Cron logs:"
echo "  - /var/log/market-pulse/hourly.log"
echo "  - /var/log/market-pulse/stock-prices.log"
echo "  - /var/log/market-pulse/historical-data.log"
echo ""
echo -e "${YELLOW}🌐 Your API should be accessible at http://localhost:8000${NC}"
echo -e "${YELLOW}📝 Make sure nginx is configured to proxy to port 8000${NC}"
