# EC2 GitHub Authentication Setup

This guide shows you how to configure your EC2 instance to authenticate with GitHub so it can pull code automatically during deployments.

## Quick Setup (Recommended Method - SSH Key)

### Step 1: Run the Setup Script

SSH into your EC2 instance and run:

```bash
cd /opt/market-pulse-v2
bash scripts/setup-github-auth.sh
```

This script will:
- Generate an SSH key pair
- Configure SSH for GitHub
- Display your public key

### Step 2: Add SSH Key to GitHub

1. **Copy the public key** displayed by the script

2. **Add to GitHub:**
   - Go to: https://github.com/settings/keys
   - Click **"New SSH key"**
   - Title: `EC2 Deploy - Market Pulse`
   - Paste the public key
   - Click **"Add SSH key"**

### Step 3: Test Connection

```bash
ssh -T git@github.com
```

You should see: `Hi USERNAME! You've successfully authenticated...`

### Step 4: Update Git Remote to Use SSH

```bash
cd /opt/market-pulse-v2

# Check current remote (likely HTTPS)
git remote -v

# Update to SSH (replace YOUR_USERNAME with your GitHub username)
git remote set-url origin git@github.com:YOUR_USERNAME/market-pulse-v2.git

# Verify it changed
git remote -v
```

### Step 5: Test Git Pull

```bash
git pull origin master
```

If successful, you're done! ✅

---

## Manual Setup (Alternative Methods)

### Method 1: Deploy Key (Repository-Specific)

If you want to limit access to just this repository:

#### On EC2:
```bash
# Generate key
ssh-keygen -t ed25519 -C "deploy-key" -f ~/.ssh/deploy_key -N ""

# Display public key
cat ~/.ssh/deploy_key.pub
```

#### On GitHub:
1. Go to your repository: `https://github.com/YOUR_USERNAME/market-pulse-v2`
2. **Settings** → **Deploy keys** → **Add deploy key**
3. Title: `EC2 Production`
4. Paste the public key
5. ✅ Check **"Allow write access"** if you need to push (optional)
6. Click **Add key**

#### Configure Git:
```bash
cd /opt/market-pulse-v2

# Update SSH config
cat >> ~/.ssh/config << 'EOF'
Host github.com-deploy
    HostName github.com
    User git
    IdentityFile ~/.ssh/deploy_key
EOF

# Update remote
git remote set-url origin git@github.com-deploy:YOUR_USERNAME/market-pulse-v2.git
```

### Method 2: Personal Access Token (HTTPS)

If you prefer HTTPS over SSH:

#### Generate Token:
1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**
2. Click **"Generate new token (classic)"**
3. Note: `EC2 Deployment`
4. Expiration: `No expiration` or your preference
5. Select scope: `repo` (Full control of private repositories)
6. Click **Generate token**
7. **Copy the token** (you won't see it again!)

#### Configure Git:
```bash
cd /opt/market-pulse-v2

# Store credentials (will prompt once for username and token)
git config credential.helper store

# Test pull (enter username and token when prompted)
git pull origin master
# Username: YOUR_GITHUB_USERNAME
# Password: ghp_YourPersonalAccessToken

# Future pulls won't require credentials
```

⚠️ **Security Note:** Token is stored in plaintext at `~/.git-credentials`

#### Better: Use Git Credential Cache (Temporary)
```bash
# Cache for 1 hour (3600 seconds)
git config --global credential.helper 'cache --timeout=3600'

# Or use AWS Secrets Manager for production
```

---

## Troubleshooting

### "Permission denied (publickey)"

**Problem:** SSH key not recognized by GitHub

**Solution:**
```bash
# 1. Verify SSH key exists
ls -la ~/.ssh/id_ed25519*

# 2. Add key to SSH agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# 3. Test GitHub connection with verbose output
ssh -vT git@github.com

# 4. Verify key is added on GitHub
# Go to: https://github.com/settings/keys
```

### "Host key verification failed"

**Problem:** GitHub's host key not in known_hosts

**Solution:**
```bash
ssh-keyscan github.com >> ~/.ssh/known_hosts
```

### "Authentication failed" (HTTPS)

**Problem:** Wrong username/password or expired token

**Solution:**
```bash
# Remove stored credentials
rm ~/.git-credentials

# Or edit and fix:
nano ~/.git-credentials

# Format should be:
# https://USERNAME:TOKEN@github.com
```

### "Could not resolve host"

**Problem:** DNS or network issue

**Solution:**
```bash
# Test DNS
nslookup github.com

# Test connectivity
ping github.com

# Check internet connection
curl -I https://github.com
```

### Git Still Asks for Password

**Problem:** Remote URL is still HTTPS

**Solution:**
```bash
cd /opt/market-pulse-v2

# Check current URL
git remote get-url origin

# If it shows https://, change to SSH:
git remote set-url origin git@github.com:YOUR_USERNAME/market-pulse-v2.git
```

---

## Verification Checklist

Run these commands to verify everything is set up correctly:

```bash
# ✅ 1. SSH key exists
ls -la ~/.ssh/id_ed25519

# ✅ 2. GitHub connection works
ssh -T git@github.com

# ✅ 3. Git remote uses SSH
cd /opt/market-pulse-v2
git remote -v
# Should show: git@github.com:...

# ✅ 4. Can pull from GitHub
git pull origin master

# ✅ 5. Project directory has correct permissions
ls -la /opt/market-pulse-v2
# Owner should be: ubuntu (or your user)
```

If all checks pass, your EC2 instance is ready for automated deployments! 🚀

---

## Security Best Practices

### SSH Keys
- ✅ Use Ed25519 keys (more secure than RSA)
- ✅ Never share private keys
- ✅ Use deploy keys for specific repositories
- ✅ Rotate keys every 90 days
- ✅ Use different keys for different environments (staging/production)

### Personal Access Tokens
- ✅ Set expiration dates
- ✅ Use minimal required scopes
- ✅ Store in AWS Secrets Manager for production
- ✅ Rotate regularly
- ✅ Revoke immediately if compromised

### File Permissions
```bash
# Correct SSH permissions
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
chmod 600 ~/.ssh/config
chmod 644 ~/.ssh/known_hosts
```

---

## Automated Setup Script Reference

The `scripts/setup-github-auth.sh` script does the following:

1. Checks for existing SSH keys (backs up if found)
2. Generates new Ed25519 SSH key pair
3. Starts SSH agent and adds key
4. Adds GitHub to known hosts
5. Configures SSH config file
6. Displays public key and next steps

**Usage:**
```bash
cd /opt/market-pulse-v2
bash scripts/setup-github-auth.sh
```

---

## Multiple Repositories

If you need to pull from multiple repositories:

```bash
# Option 1: Use the same SSH key for all (simpler)
# Just add the same public key to GitHub once
# It will work for all repositories

# Option 2: Use different keys per repository (more secure)
cat >> ~/.ssh/config << 'EOF'
Host github.com-repo1
    HostName github.com
    IdentityFile ~/.ssh/id_ed25519_repo1

Host github.com-repo2
    HostName github.com
    IdentityFile ~/.ssh/id_ed25519_repo2
EOF

# Then set remote URLs accordingly:
git remote set-url origin git@github.com-repo1:user/repo1.git
```

---

## Next Steps After Setup

Once GitHub authentication is working:

1. **Test the CI/CD pipeline** - Push a small change to master
2. **Monitor deployment** - Check GitHub Actions logs
3. **Verify on EC2** - Check that code updated and service restarted
4. **Set up monitoring** - Add alerts for failed deployments

---

*Last Updated: October 6, 2025*
