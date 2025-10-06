#!/bin/bash
# Setup GitHub authentication on EC2 instance
# Run this script on your EC2 instance

set -e

echo "🔑 Setting up GitHub authentication for EC2..."

# Check if SSH key already exists
if [ -f ~/.ssh/id_ed25519 ]; then
    echo "⚠️  SSH key already exists at ~/.ssh/id_ed25519"
    read -p "Generate a new key? This will backup the old one. (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mv ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.backup
        mv ~/.ssh/id_ed25519.pub ~/.ssh/id_ed25519.pub.backup
        echo "✅ Backed up existing keys"
    else
        echo "Using existing key..."
    fi
fi

# Generate SSH key if it doesn't exist
if [ ! -f ~/.ssh/id_ed25519 ]; then
    echo "📝 Generating new SSH key..."
    ssh-keygen -t ed25519 -C "ec2-github-deploy" -f ~/.ssh/id_ed25519 -N ""
    echo "✅ SSH key generated"
fi

# Start SSH agent and add key
echo "🔐 Adding key to SSH agent..."
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# Configure SSH for GitHub
echo "⚙️  Configuring SSH..."
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Add GitHub to known hosts if not already there
if ! grep -q "github.com" ~/.ssh/known_hosts 2>/dev/null; then
    ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null
    echo "✅ Added GitHub to known hosts"
fi

# Create/update SSH config for GitHub
if ! grep -q "Host github.com" ~/.ssh/config 2>/dev/null; then
    cat >> ~/.ssh/config << 'EOF'

# GitHub Configuration
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
EOF
    chmod 600 ~/.ssh/config
    echo "✅ Updated SSH config"
fi

# Display the public key
echo ""
echo "======================================================================"
echo "📋 Your SSH Public Key (copy this):"
echo "======================================================================"
echo ""
cat ~/.ssh/id_ed25519.pub
echo ""
echo "======================================================================"
echo ""
echo "📌 Next Steps:"
echo ""
echo "1. Copy the SSH public key above"
echo ""
echo "2. Add it to GitHub:"
echo "   • Go to: https://github.com/settings/keys"
echo "   • Click 'New SSH key'"
echo "   • Title: 'EC2 Deploy Key' (or any name)"
echo "   • Paste the key"
echo "   • Click 'Add SSH key'"
echo ""
echo "3. Test the connection:"
echo "   ssh -T git@github.com"
echo ""
echo "4. Update your git remote to use SSH:"
echo "   cd /opt/market-pulse-v2"
echo "   git remote set-url origin git@github.com:YOUR_USERNAME/market-pulse-v2.git"
echo ""
echo "======================================================================"
