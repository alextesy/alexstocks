# CI/CD Deployment Setup Guide

This guide explains how to set up automated deployment to EC2 via GitHub Actions.

## Overview

The CI/CD pipeline automatically deploys to EC2 when:
- Code is pushed to the `master` branch
- All tests, linting, and security checks pass

## Required GitHub Secrets

You need to configure the following secrets in your GitHub repository:

### 1. Navigate to GitHub Secrets

1. Go to your repository on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** for each secret below

### 2. Configure Secrets

#### `EC2_SSH_KEY`
Your EC2 instance's private SSH key.

**How to get it:**
```bash
# On your local machine, display your SSH private key
cat ~/.ssh/your-ec2-key.pem
```

- Copy the entire content including `-----BEGIN RSA PRIVATE KEY-----` and `-----END RSA PRIVATE KEY-----`
- Paste it as the secret value

#### `EC2_HOST`
Your EC2 instance's Elastic IP address.

**Example:** `54.123.45.67`

**How to get it:**
- AWS Console → EC2 → Instances
- Find your instance's **Elastic IP** or **Public IPv4 address**

#### `EC2_USER`
The SSH user for your EC2 instance.

**For Ubuntu instances:** `ubuntu`

**For Amazon Linux instances:** `ec2-user`

#### `DOMAIN` (Optional)
Your domain name for public health checks.

**Example:** `alexstocks.com`

- Only needed if you want to verify the public URL after deployment
- Can be omitted if you only want to check localhost

## EC2 Instance Setup

### 1. Ensure Git Repository is Set Up

On your EC2 instance:

```bash
# Navigate to project directory
cd /opt/market-pulse-v2

# Initialize git if not already done
git init
git remote add origin https://github.com/YOUR_USERNAME/market-pulse-v2.git

# Or verify existing remote
git remote -v

# Ensure you're on master branch
git checkout master
```

### 2. Configure Git Authentication

For **public repositories:**
```bash
# No authentication needed for pulling
git pull origin master
```

For **private repositories**, choose one option:

#### Option A: SSH Key (Recommended)
```bash
# Generate SSH key on EC2
ssh-keygen -t ed25519 -C "ec2-deploy"

# Display public key
cat ~/.ssh/id_ed25519.pub

# Add this public key to GitHub:
# GitHub → Settings → SSH and GPG keys → New SSH key

# Update git remote to use SSH
git remote set-url origin git@github.com:YOUR_USERNAME/market-pulse-v2.git
```

#### Option B: Personal Access Token
```bash
# Create token: GitHub → Settings → Developer settings → Personal access tokens
# Generate new token with 'repo' scope

# Store credentials
git config credential.helper store

# On next pull, enter username and token as password
git pull origin master
```

### 3. Configure Passwordless Sudo (for service restart)

```bash
# Edit sudoers file
sudo visudo

# Add this line at the end (replace 'ubuntu' with your user):
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart market-pulse, /bin/systemctl is-active market-pulse, /usr/bin/chown
```

This allows the deployment script to restart the service without password prompts.

## Deployment Flow

When you push to `master`:

1. **Tests Run** - Unit tests, linting, security scans
2. **Build** - Package is built and artifacts uploaded
3. **Deploy** - If tests pass:
   - SSH into EC2
   - Pull latest code from git
   - Restart the systemd service
   - Verify the service is running
4. **Verify** - Health check on public domain

## Testing the Deployment

### Manual Test

Push a small change to master:

```bash
# Make a small change
echo "# CI/CD Test" >> README.md
git add README.md
git commit -m "test: CI/CD deployment"
git push origin master
```

### Monitor Deployment

1. Go to GitHub → Actions tab
2. Watch the workflow run
3. Check the "Deploy to EC2" job logs

### Verify on EC2

```bash
# Check service status
sudo systemctl status market-pulse

# View recent logs
sudo journalctl -u market-pulse -n 50

# Check git status
cd /opt/market-pulse-v2
git log -1
```

## Deployment Only for Specific Branches

Currently configured to deploy only from `master`. To add other branches:

Edit [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

```yaml
deploy:
  name: Deploy to EC2
  runs-on: ubuntu-latest
  needs: [test, lint, security, build]
  # Change this line to include other branches:
  if: github.event_name == 'push' && (github.ref == 'refs/heads/master' || github.ref == 'refs/heads/production')
```

## Environment-Specific Deployments

For staging vs production deployments:

### Option 1: Branch-Based

```yaml
deploy-staging:
  if: github.ref == 'refs/heads/develop'
  # Use staging EC2 secrets

deploy-production:
  if: github.ref == 'refs/heads/master'
  # Use production EC2 secrets
```

### Option 2: Environment Secrets

Use GitHub Environments:

1. GitHub → Settings → Environments
2. Create "staging" and "production" environments
3. Add environment-specific secrets
4. Reference in workflow:

```yaml
deploy:
  environment: production  # or staging
  env:
    SSH_HOST: ${{ secrets.EC2_HOST }}
```

## Rollback Strategy

If a deployment fails or causes issues:

### On EC2

```bash
cd /opt/market-pulse-v2

# View recent commits
git log --oneline -5

# Rollback to previous commit
git reset --hard <previous-commit-hash>

# Restart service
sudo systemctl restart market-pulse
```

### Automated Rollback

Add to deployment script (advanced):

```yaml
- name: Deploy to EC2
  run: |
    ssh -i ~/.ssh/deploy_key $SSH_USER@$SSH_HOST << 'EOF'
      cd /opt/market-pulse-v2

      # Save current commit
      PREVIOUS_COMMIT=$(git rev-parse HEAD)

      # Pull and deploy
      git pull origin master
      sudo systemctl restart market-pulse
      sleep 5

      # Health check
      if ! curl -f http://localhost:8000/health; then
        echo "⚠️ Health check failed, rolling back..."
        git reset --hard $PREVIOUS_COMMIT
        sudo systemctl restart market-pulse
        exit 1
      fi
    EOF
```

## Security Best Practices

1. **Rotate SSH Keys Regularly**
   - Generate new EC2 key pair every 90 days
   - Update GitHub secret

2. **Use Deploy Keys** (for private repos)
   - Instead of personal SSH keys, use deploy keys with read-only access
   - GitHub → Repository Settings → Deploy keys

3. **Limit Secret Access**
   - Use GitHub Environments with required reviewers for production
   - Restrict who can approve production deployments

4. **Audit Deployments**
   - Review GitHub Actions logs regularly
   - Set up alerts for failed deployments

5. **Environment Variables**
   - Never commit `.env` files
   - Sensitive env vars should remain on EC2, not in CI/CD

## Troubleshooting

### SSH Connection Fails

**Error:** `Permission denied (publickey)`

```bash
# Verify secret is correctly formatted
# Should include headers: -----BEGIN RSA PRIVATE KEY-----

# Check EC2 security group allows SSH from GitHub Actions IPs
# May need to allow SSH from 0.0.0.0/0 or use GitHub's IP ranges
```

### Git Pull Fails

**Error:** `Authentication failed`

```bash
# On EC2, test git pull manually
cd /opt/market-pulse-v2
git pull origin master

# If it prompts for password, set up SSH key or PAT (see above)
```

### Service Restart Fails

**Error:** `sudo: a password is required`

```bash
# Configure passwordless sudo (see EC2 Instance Setup above)
sudo visudo
```

### Health Check Fails

**Error:** `curl: (7) Failed to connect`

```bash
# On EC2, check if service is running
sudo systemctl status market-pulse

# Check logs
sudo journalctl -u market-pulse -n 100

# Verify port 8000 is listening
sudo ss -tlnp | grep 8000
```

## Advanced: Database Migrations

If your deployment includes database changes:

### Add Migration Step

Edit [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

```yaml
- name: Deploy to EC2
  run: |
    ssh -i ~/.ssh/deploy_key $SSH_USER@$SSH_HOST << 'EOF'
      cd /opt/market-pulse-v2
      git pull origin master

      # Run migrations before restarting
      uv run alembic upgrade head

      sudo systemctl restart market-pulse
    EOF
```

### Backup Database Before Deployment

```yaml
- name: Backup Database
  run: |
    ssh -i ~/.ssh/deploy_key $SSH_USER@$SSH_HOST << 'EOF'
      cd /opt/market-pulse-v2

      # Create backup
      BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).custom"
      docker compose exec -T postgres pg_dump -U postgres -Fc market_pulse > ~/backups/$BACKUP_FILE

      echo "✅ Backup created: $BACKUP_FILE"
    EOF
```

## Monitoring Deployments

### Slack/Discord Notifications

Add notification step:

```yaml
- name: Notify Slack
  if: always()
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK_URL }}
    payload: |
      {
        "text": "Deployment ${{ job.status }}: ${{ github.repository }}"
      }
```

### Email Notifications

Use GitHub's built-in notifications:
- GitHub → Settings → Notifications
- Enable "Actions" notifications

## Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Deployment Best Practices](https://docs.github.com/en/actions/deployment/about-deployments/deploying-with-github-actions)

---

*Last Updated: October 6, 2025*
