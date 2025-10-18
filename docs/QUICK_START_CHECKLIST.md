# Quick Start Checklist - ECS Migration

**Print this and check off as you go!** ✅

---

## Pre-Flight (10 minutes)

- [ ] On `refactor/create-lambdas` branch
- [ ] AWS credentials configured (`aws sts get-caller-identity`)
- [ ] Backup EC2 crontab: `ssh ubuntu@ec2 "crontab -l > ~/crontab_backup.txt"`
- [ ] Gather AWS info:
  - [ ] VPC ID: ________________
  - [ ] Private Subnet IDs: ________________
  - [ ] Postgres Security Group ID: ________________

---

## Phase 1: Local Testing (15 min)

- [ ] `make build-jobs-image` (succeeds)
- [ ] `make up` (local services start)
- [ ] `uv run uvicorn app.main:app` (web app works)
- [ ] Visit http://localhost:8000 (loads correctly)

---

## Phase 2: Deploy Infrastructure (45 min)

- [ ] `git push origin refactor/create-lambdas`
- [ ] `./scripts/setup-aws-secrets.sh` (create AWS secrets)
- [ ] `cd infrastructure/terraform`
- [ ] `cp terraform.tfvars.example terraform.tfvars`
- [ ] Edit `terraform.tfvars` with your AWS details
- [ ] `terraform init`
- [ ] `terraform plan` (review resources)
- [ ] `terraform apply` (type 'yes')
- [ ] `cd ../..` (back to root)
- [ ] `make ecr-login`
- [ ] `make push-jobs-image` (wait 5-10 min)

---

## Phase 3: Test ECS Jobs (45 min)

### Reddit Scraper
- [ ] `make ecs-run-scraper`
- [ ] `make ecs-logs-scraper` (watch for success)
- [ ] No errors in logs

### Sentiment Analysis
- [ ] `make ecs-run-sentiment`
- [ ] `make ecs-logs-sentiment` (watch for success)
- [ ] No errors in logs

### Database Verification
- [ ] SSH to EC2: `ssh ubuntu@ec2`
- [ ] Check articles: `psql $DATABASE_URL -c "SELECT COUNT(*) FROM articles WHERE created_at > NOW() - INTERVAL '1 hour';"`
- [ ] Articles found: ________ (should be > 0)
- [ ] Check sentiment: `psql $DATABASE_URL -c "SELECT COUNT(*) FROM articles WHERE sentiment IS NOT NULL AND updated_at > NOW() - INTERVAL '1 hour';"`
- [ ] Sentiment updates: ________ (should be > 0)
- [ ] `exit` (logout from EC2)

---

## Phase 4: Cutover (20 min)

### Disable EC2 Crons
- [ ] `ssh ubuntu@ec2`
- [ ] `crontab -e`
- [ ] Comment out market-pulse cron lines (add `#` at start)
- [ ] Save and exit
- [ ] `crontab -l` (verify changes)
- [ ] `exit`

### Enable ECS Schedules
- [ ] `make schedule-enable-all`
- [ ] `make schedule-status` (verify ENABLED)

### Monitor First Run
- [ ] Terminal 1: `make ecs-logs-scraper`
- [ ] Terminal 2: `make ecs-logs-sentiment`
- [ ] Wait up to 15 minutes for first scheduled run
- [ ] Both jobs complete successfully

### Verify Web App
- [ ] Visit https://alexstocks.com (or your domain)
- [ ] Homepage loads
- [ ] Ticker pages work
- [ ] Recent articles appear

---

## Phase 5: App Optimization (Optional - 45 min)

**Do this AFTER cutover is stable (24-48 hours later)**

- [ ] Edit `pyproject.toml` (split dependencies)
- [ ] Create `Dockerfile.prod` (optimized)
- [ ] `docker build -f Dockerfile.prod -t market-pulse-app-optimized .`
- [ ] Test locally: `docker run -p 8000:8000 --env-file .env market-pulse-app-optimized`
- [ ] Visit http://localhost:8000 (verify works)
- [ ] Deploy to EC2:
  - [ ] `ssh ubuntu@ec2`
  - [ ] `cd ~/market-pulse-v2`
  - [ ] `git pull origin refactor/create-lambdas`
  - [ ] `source .venv/bin/activate`
  - [ ] `uv sync`
  - [ ] `sudo systemctl restart market-pulse`
  - [ ] `sudo journalctl -u market-pulse -f` (check logs)
  - [ ] `exit`
- [ ] `curl https://alexstocks.com/health` (returns {"status":"ok"})

---

## Phase 6: Monitoring (Ongoing)

### Day 1
- [ ] Check ECS logs every 2-3 hours
- [ ] Check web app still works
- [ ] Check database has continuous data

### Day 2-7
- [ ] Check ECS logs daily
- [ ] Check web app daily
- [ ] Monitor AWS costs in billing console

### After 1 Week
- [ ] Delete old crontab backups on EC2
- [ ] Update team documentation
- [ ] Celebrate cost savings! 🎉

---

## Rollback (If Needed)

**If ECS jobs fail:**
1. `ssh ubuntu@ec2`
2. `crontab ~/crontab_backup.txt`
3. `crontab -l` (verify)
4. `exit`
5. `make schedule-disable-all`

**If web app breaks:**
1. `ssh ubuntu@ec2`
2. `cd ~/market-pulse-v2`
3. `git log --oneline -5`
4. `git checkout <previous-commit>`
5. `uv sync`
6. `sudo systemctl restart market-pulse`

---

## Success Checklist

After 1 week, you should have:

- [x] Web app running normally on EC2
- [x] ECS jobs running every 15 minutes
- [x] No errors in CloudWatch logs
- [x] Continuous data in database
- [x] Old EC2 crons disabled
- [x] ~90% cost reduction on jobs
- [x] Optional: Smaller Docker image for web app

---

**Total Estimated Time:** 2-4 hours (can spread over multiple days)

**Questions?** See [COMPLETE_MIGRATION_PLAN.md](COMPLETE_MIGRATION_PLAN.md) for detailed steps.
