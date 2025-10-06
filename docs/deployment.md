# Market Pulse - EC2 Deployment Guide

This document provides a complete guide for deploying Market Pulse to AWS EC2 with a custom domain.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [EC2 Instance Setup](#ec2-instance-setup)
3. [Database Setup](#database-setup)
4. [Domain Configuration](#domain-configuration)
5. [SSL/HTTPS Setup](#sslhttps-setup)
6. [Monitoring & Logs](#monitoring--logs)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Local Machine
- Database dump file (created locally)
- SSH access to EC2 instance
- Domain name purchased and accessible

### AWS EC2
- Ubuntu instance running
- Elastic IP assigned to the instance
- Security group configured with:
  - Port 22 (SSH) - Your IP
  - Port 80 (HTTP) - 0.0.0.0/0
  - Port 443 (HTTPS) - 0.0.0.0/0

---

## EC2 Instance Setup

### 1. Initial Software Installation

SSH into your EC2 instance and install required software:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ubuntu

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/activate  # or wherever uv is installed

# Install nginx
sudo apt install -y nginx

# Install make
sudo apt install -y make
```

### 2. Project Setup

```bash
# Create project directory
sudo mkdir -p /opt/market-pulse-v2
sudo chown -R ubuntu:ubuntu /opt/market-pulse-v2

# Transfer project files from local machine
# From your local machine:
scp -r /Users/alex/market-pulse-v2 ubuntu@YOUR_ELASTIC_IP:/opt/

# Or clone from git
cd /opt
git clone <your-repo-url> market-pulse-v2
cd market-pulse-v2
```

### 3. Environment Configuration

Create `.env` file with required variables:

```bash
cd /opt/market-pulse-v2
nano .env
```

Add the following (replace with your actual values):

```bash
POSTGRES_PASSWORD=your_secure_password
POSTGRES_URL=postgresql+psycopg://postgres:your_secure_password@localhost:5432/market_pulse
OPENAI_API_KEY=your_openai_api_key
```

**Important Notes:**
- The API runs directly on the host (not in Docker), so use `localhost` for database connection
- Database name must be `market_pulse`
- Database user must be `postgres`

---

## Database Setup

### 1. Create Database Dump (Local Machine)

```bash
# Navigate to project directory
cd /Users/alex/market-pulse-v2

# Create dump in custom format (handles special characters better)
docker compose exec -T postgres pg_dump -U postgres -Fc market_pulse > market_pulse_dump.custom

# Verify dump was created
ls -lh market_pulse_dump.custom
```

### 2. Transfer Dump to EC2

```bash
# From local machine
scp market_pulse_dump.custom ubuntu@YOUR_ELASTIC_IP:~/
```

### 3. Restore Database on EC2

```bash
# On EC2
cd /opt/market-pulse-v2

# Start PostgreSQL container
docker compose up -d postgres
sleep 10

# Restore the dump
docker compose exec -T postgres pg_restore -U postgres -d market_pulse -v < ~/market_pulse_dump.custom

# Verify data was restored
docker compose exec postgres psql -U postgres market_pulse -c "SELECT COUNT(*) FROM article; SELECT COUNT(*) FROM ticker;"
```

---

## Domain Configuration

### 1. Set Up Nginx Reverse Proxy

```bash
cd /opt/market-pulse-v2
./scripts/nginx-setup.sh
# Enter your domain when prompted (e.g., alexstocks.com)
```

Or manually create the nginx configuration:

```bash
sudo nano /etc/nginx/sites-available/market-pulse
```

Add:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }

    client_max_body_size 10M;
}
```

Enable the site:

```bash
sudo ln -sf /etc/nginx/sites-available/market-pulse /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### 2. Configure DNS Records

In your domain registrar (GoDaddy, Namecheap, etc.):

1. **Add A Record for root domain:**
   - Type: `A`
   - Name: `@`
   - Value: `YOUR_ELASTIC_IP`
   - TTL: `1 Hour`

2. **Add A Record for www:**
   - Type: `A`
   - Name: `www`
   - Value: `YOUR_ELASTIC_IP`
   - TTL: `1 Hour`

3. **Delete any existing CNAME records** that point to parking services (e.g., domainconnect.gd.domaincontrol.com)

4. **Verify DNS propagation** (wait 5-15 minutes):

```bash
dig your-domain.com +short
# Should show: YOUR_ELASTIC_IP
```

---

## Application Deployment

### Automated Setup

Run the automated setup script:

```bash
cd /opt/market-pulse-v2
./scripts/ec2-setup.sh
```

This script will:
- ✅ Verify environment variables
- ✅ Create log directories
- ✅ Start PostgreSQL
- ✅ Restore database (if dump exists)
- ✅ Create systemd service
- ✅ Set up cron jobs
- ✅ Start the application

### Manual Setup

If you prefer manual setup or need to troubleshoot:

#### 1. Create Systemd Service

```bash
# Find uv location
which uv  # Usually /home/ubuntu/.local/bin/uv

# Create service file
sudo nano /etc/systemd/system/market-pulse.service
```

Add:

```ini
[Unit]
Description=Market Pulse API
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/market-pulse-v2
Environment="PATH=/home/ubuntu/.local/bin:/home/ubuntu/.cargo/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/market-pulse-v2/.env
ExecStartPre=/usr/bin/docker compose up -d postgres
ExecStartPre=/bin/sleep 5
ExecStart=/home/ubuntu/.local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable market-pulse
sudo systemctl start market-pulse
sudo systemctl status market-pulse
```

#### 2. Set Up Cron Jobs

```bash
# Create log directory
sudo mkdir -p /var/log/market-pulse
sudo chown ubuntu:ubuntu /var/log/market-pulse

# Edit crontab
crontab -e
```

Add:

```cron
# Market Pulse Jobs
PATH=/home/ubuntu/.local/bin:/home/ubuntu/.cargo/bin:/usr/local/bin:/usr/bin:/bin

# Reddit scraping + sentiment analysis (every hour at :13)
13 * * * * cd /opt/market-pulse-v2 && uv run python app/jobs/scrape_and_analyze.py comments >> /var/log/market-pulse/hourly.log 2>&1

# Stock prices every 15min during market hours (6:30 AM - 1:00 PM PT)
*/15 6-13 * * 1-5 cd /opt/market-pulse-v2 && uv run python app/scripts/collect_stock_data_smart.py --type current >> /var/log/market-pulse/stock-prices.log 2>&1

# Historical data once daily at 2:00 PM PT
0 14 * * 1-5 cd /opt/market-pulse-v2 && uv run python app/scripts/collect_stock_data_smart.py --type historical --period 1mo >> /var/log/market-pulse/historical-data.log 2>&1

# Weekend collection (reduced frequency - hourly)
0 * * * 0,6 cd /opt/market-pulse-v2 && uv run python app/scripts/collect_stock_data_smart.py --type current >> /var/log/market-pulse/stock-prices-weekend.log 2>&1
```

---

## SSL/HTTPS Setup

### Install Certbot

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
```

### Get SSL Certificate

```bash
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

Follow the prompts:
- Enter your email address
- Agree to terms of service
- Choose whether to redirect HTTP to HTTPS (recommended: **Yes**)

Certbot will automatically:
- Obtain SSL certificates from Let's Encrypt
- Update nginx configuration
- Set up auto-renewal (certificates expire every 90 days)

### Test Auto-Renewal

```bash
sudo certbot renew --dry-run
```

### Manual Certificate Renewal

Certificates auto-renew, but you can manually renew if needed:

```bash
sudo certbot renew
sudo systemctl reload nginx
```

---

## Monitoring & Logs

### Service Management

```bash
# Check service status
sudo systemctl status market-pulse

# View live logs
sudo journalctl -u market-pulse -f

# Restart service
sudo systemctl restart market-pulse

# Stop service
sudo systemctl stop market-pulse

# Start service
sudo systemctl start market-pulse
```

### Application Logs

```bash
# Cron job logs
tail -f /var/log/market-pulse/hourly.log
tail -f /var/log/market-pulse/stock-prices.log
tail -f /var/log/market-pulse/historical-data.log

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Database Access

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U postgres market_pulse

# Inside psql:
\dt                          # List tables
SELECT COUNT(*) FROM article;
SELECT COUNT(*) FROM ticker;
\q                          # Exit
```

### Health Checks

```bash
# Test API locally
curl http://localhost:8000

# Test domain
curl http://your-domain.com

# Check database connectivity
docker compose exec postgres psql -U postgres market_pulse -c "SELECT 1;"

# Check disk space
df -h

# Check memory usage
free -h

# Check running containers
docker ps
```

---

## Troubleshooting

### Service Won't Start

**Error: Status 203/EXEC**
```bash
# Check uv location
which uv

# Update systemd service with correct path
sudo nano /etc/systemd/system/market-pulse.service
# Update ExecStart line with correct path to uv

sudo systemctl daemon-reload
sudo systemctl restart market-pulse
```

**Error: Database connection failed**
```bash
# Verify .env file
cat /opt/market-pulse-v2/.env

# Ensure POSTGRES_URL uses 'localhost' not 'postgres' or 'host.docker.internal'
# Correct: postgresql+psycopg://postgres:password@localhost:5432/market_pulse

# Test database connectivity
docker compose exec postgres psql -U postgres market_pulse -c "SELECT 1;"
```

**Error: torch/Python version mismatch**
```bash
# Update pyproject.toml
nano /opt/market-pulse-v2/pyproject.toml

# Change:
# torch>=2.2.0  (for Python 3.12)
# torchvision>=0.17.0

# Restart service
sudo systemctl restart market-pulse
```

### DNS Issues

**Domain not resolving to EC2**
```bash
# Check DNS
dig your-domain.com +short

# Should show your Elastic IP
# If not, verify:
# 1. A records are correct in registrar
# 2. No CNAME records pointing to parking services
# 3. Wait 5-15 minutes for propagation
```

**SSL Certificate Fails**
```bash
# Ensure DNS is working first
dig your-domain.com +short

# Check nginx config
sudo cat /etc/nginx/sites-enabled/market-pulse | grep server_name

# Try standalone mode
sudo systemctl stop nginx
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com
sudo systemctl start nginx
sudo certbot install --nginx
```

### Database Issues

**Database restore errors**
```bash
# Clean slate - remove all data
cd /opt/market-pulse-v2
docker compose down -v

# Start fresh
docker compose up -d postgres
sleep 10

# Restore dump
docker compose exec -T postgres pg_restore -U postgres -d market_pulse -v < ~/market_pulse_dump.custom
```

**Duplicate key errors**
- Database was already partially restored
- Solution: Run `docker compose down -v` to remove volumes, then restore again

### Nginx Issues

**502 Bad Gateway**
```bash
# Check if app is running
sudo systemctl status market-pulse
curl http://localhost:8000

# Check nginx config
sudo nginx -t

# Restart both
sudo systemctl restart market-pulse
sudo systemctl restart nginx
```

**Connection refused**
```bash
# Verify app is listening on 8000
sudo ss -tlnp | grep 8000

# Check service logs
sudo journalctl -u market-pulse -n 100
```

---

## Architecture Overview

```
User Browser
    ↓
Domain (your-domain.com) → DNS A Record
    ↓
AWS EC2 (Elastic IP)
    ↓
Nginx (Port 80/443) → Reverse Proxy
    ↓
FastAPI App (Port 8000) → Running via systemd + uv
    ↓
PostgreSQL (Port 5432) → Running in Docker
```

### Key Files & Directories

```
/opt/market-pulse-v2/               # Project directory
├── .env                            # Environment variables
├── docker-compose.yml              # Docker configuration
├── app/                            # Application code
├── scripts/
│   ├── ec2-setup.sh               # Automated setup script
│   └── nginx-setup.sh             # Nginx configuration script
└── docs/
    └── deployment.md              # This file

/etc/nginx/sites-available/market-pulse  # Nginx config
/etc/systemd/system/market-pulse.service # Systemd service
/var/log/market-pulse/              # Application logs
~/market_pulse_dump.custom          # Database dump
```

---

## Update & Maintenance

### Deploying Code Updates

```bash
# On EC2
cd /opt/market-pulse-v2

# Pull latest changes (if using git)
git pull origin main

# Or transfer updated files from local
# From local: scp -r app/ ubuntu@YOUR_ELASTIC_IP:/opt/market-pulse-v2/

# Restart service
sudo systemctl restart market-pulse

# Check status
sudo systemctl status market-pulse
```

### Database Migrations

```bash
cd /opt/market-pulse-v2

# Run migration scripts
uv run python -m app.scripts.migration_name

# Or connect directly
docker compose exec postgres psql -U postgres market_pulse
```

### Updating Dependencies

```bash
cd /opt/market-pulse-v2

# Update pyproject.toml with new dependencies
nano pyproject.toml

# Restart service (uv will auto-install new deps)
sudo systemctl restart market-pulse
```

---

## Security Recommendations

1. **Change default passwords** - Use strong, unique passwords for PostgreSQL
2. **Restrict SSH access** - Limit EC2 security group to your IP only
3. **Enable HTTPS** - Always use SSL certificates
4. **Keep system updated** - Regular `apt update && apt upgrade`
5. **Monitor logs** - Check for suspicious activity
6. **Backup database** - Regular database dumps
7. **Use secrets manager** - Consider AWS Secrets Manager for production

---

## Production Checklist

- [ ] Elastic IP assigned and stable
- [ ] Security groups properly configured
- [ ] Domain DNS pointing to Elastic IP
- [ ] SSL certificate installed and working
- [ ] Database backed up and restored
- [ ] Environment variables configured
- [ ] Systemd service enabled and running
- [ ] Cron jobs scheduled
- [ ] Nginx reverse proxy working
- [ ] Application accessible via domain
- [ ] Logs rotating properly
- [ ] Monitoring set up
- [ ] SSL auto-renewal tested

---

## Support & Resources

- **FastAPI Documentation**: https://fastapi.tiangolo.com
- **Let's Encrypt**: https://letsencrypt.org
- **Nginx Documentation**: https://nginx.org/en/docs/
- **Docker Compose**: https://docs.docker.com/compose/
- **uv Package Manager**: https://github.com/astral-sh/uv

---

*Last Updated: October 6, 2025*
