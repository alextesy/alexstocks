# Staging Environment Runbook

Use this guide to launch a production-parity web app host, deploy any branch, validate it against the shared production database, and then tear the host down to control spend.

## 1. Launch the Host

1. Capture/refresh the production AMI as described in [`docs/STAGING_BASELINE.md`](STAGING_BASELINE.md).
2. Update `infrastructure/webapp-staging/terraform.tfvars` with:
   - `ami_id` (latest prod AMI)
   - `subnet_id`, `security_group_ids`, `instance_profile`
   - `ssh_key_name`
3. Deploy the instance:
   ```bash
   cd infrastructure/webapp-staging
   terraform init
   terraform apply -auto-approve
   ```
4. Save the resulting instance ID + hostname into `scripts/staging.conf`.
5. When the box is stopped, run `scripts/staging-start.sh` to bring it up on demand.

## 2. Deploy a Branch

Trigger the `Staging Deploy` workflow from GitHub Actions (`Actions` → `Staging Deploy` → `Run workflow`):

- `branch`: feature branch you want to test.
- `instance_id`: value from Terraform output or `scripts/staging.conf`.
- `staging_host`: DNS or IP reachable from GitHub runners.
- `deploy_window_minutes`: reminder duration printed at the end (does not auto-stop yet).
- `healthcheck_path`: usually `/health`.

The workflow will:
1. Start the EC2 instance (if stopped).
2. SSH in, pull the requested branch, and restart the `market-pulse` systemd service.
3. Hit HTTPS + HTTP health checks and fail fast if either is unhealthy.

## 3. Validate

While the instance is up:
- Run manual smoke tests against the public host (UI + API flows).
- Confirm background behaviors (e.g., `/v1/articles`, `/health`).
- If you need database migrations, apply them exactly as you would in production—they target the shared DB.

## 4. Tear Down

Once you're done testing:

```bash
./scripts/staging-stop.sh
```

This stops the EC2 instance but leaves the EBS volume intact, so the next start is fast and keeps the working tree + virtualenv intact. Destroy completely when you no longer need staging:

```bash
cd infrastructure/webapp-staging
terraform destroy
```

## 5. Promote to Production

After validating the branch:
1. Open/merge the PR to `master`.
2. Allow the existing `CI Pipeline` + `Deploy to EC2` job to run (unchanged).
3. Optionally tag the release so you can rebuild the AMI for the next staging cycle.
