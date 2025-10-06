#!/bin/bash
set -e

echo "🌐 Nginx Setup for Market Pulse"
echo "==============================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get domain name
read -p "Enter your domain name (e.g., example.com): " DOMAIN

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}❌ Domain name is required${NC}"
    exit 1
fi

echo -e "\n${YELLOW}📝 Creating nginx configuration for $DOMAIN${NC}"

# Create nginx config
sudo tee /etc/nginx/sites-available/market-pulse > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;

        # Increase timeout for long-running requests
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }

    # Larger client body size for file uploads
    client_max_body_size 10M;
}
EOF

echo -e "${GREEN}✅ Nginx config created${NC}"

# Enable the site
echo -e "\n${YELLOW}🔗 Enabling site${NC}"
sudo ln -sf /etc/nginx/sites-available/market-pulse /etc/nginx/sites-enabled/

# Remove default if exists
if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo -e "${GREEN}✅ Removed default config${NC}"
fi

# Test nginx config
echo -e "\n${YELLOW}🧪 Testing nginx configuration${NC}"
if sudo nginx -t; then
    echo -e "${GREEN}✅ Nginx config is valid${NC}"
else
    echo -e "${RED}❌ Nginx config has errors${NC}"
    exit 1
fi

# Restart nginx
echo -e "\n${YELLOW}🔄 Restarting nginx${NC}"
sudo systemctl restart nginx
echo -e "${GREEN}✅ Nginx restarted${NC}"

# Check if certbot is installed
if command -v certbot &> /dev/null; then
    echo -e "\n${YELLOW}🔒 Certbot is installed${NC}"
    read -p "Do you want to set up SSL with Let's Encrypt? (y/n): " SETUP_SSL

    if [ "$SETUP_SSL" = "y" ]; then
        echo -e "${YELLOW}🔒 Setting up SSL...${NC}"
        sudo certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN"
        echo -e "${GREEN}✅ SSL configured!${NC}"
    fi
else
    echo -e "\n${YELLOW}💡 To set up SSL later, run:${NC}"
    echo "sudo apt install -y certbot python3-certbot-nginx"
    echo "sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
fi

echo -e "\n${GREEN}================================${NC}"
echo -e "${GREEN}✅ Nginx Setup Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo -e "Your site should be accessible at:"
echo -e "  ${GREEN}http://$DOMAIN${NC}"
echo -e "  ${GREEN}http://www.$DOMAIN${NC}"
echo ""
echo -e "${YELLOW}⚠️  Make sure:${NC}"
echo "  1. Your domain's A record points to your Elastic IP"
echo "  2. EC2 security group allows port 80 (and 443 for HTTPS)"
echo "  3. Market Pulse service is running on port 8000"
echo ""
echo "Check nginx logs: sudo tail -f /var/log/nginx/error.log"
