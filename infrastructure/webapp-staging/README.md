# Web App Staging Terraform

This lightweight Terraform stack launches a single EC2 instance that mirrors the production web application host. Point it at an AMI captured from production and it will reproduce the same configuration while tagging resources so GitHub Actions can deploy branches for verification.

## Inputs

See [`variables.tf`](variables.tf) for the full list. The essentials:

| Variable | Description |
|----------|-------------|
| `ami_id` | AMI created from the prod EC2 instance (ensures identical stack) |
| `subnet_id` | Subnet with access to the shared Postgres + Redis |
| `security_group_ids` | SGs that allow SSH (your IP), HTTP/HTTPS (0.0.0.0/0), and DB access |
| `instance_profile` | IAM profile matching the prod host (S3 backups, Secrets Manager, etc.) |
| `ssh_key_name` | Key pair for manual debugging |
| `default_branch` | Tag used by automation to describe the staged branch |

## Usage

```bash
cd infrastructure/webapp-staging
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply -var="deployment_target=staging"
```

Stopping the instance when not in use keeps costs low:

```bash
terraform apply -var="deployment_target=staging" -var="ami_id=ami-..." -auto-approve
aws ec2 stop-instances --instance-ids "$(terraform output -raw instance_id)"
```

To destroy entirely:

```bash
terraform destroy -auto-approve
```

## User Data (Optional)

Use `user_data_base64` to pass a base64-encoded shell script (e.g., generated from `scripts/ec2-setup.sh` + a git clone). Leave it empty if the AMI already contains the repo and systemd service.

