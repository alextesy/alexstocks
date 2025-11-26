#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF_FILE="$ROOT_DIR/scripts/staging.conf"

if [[ ! -f "$CONF_FILE" ]]; then
  echo "Missing $CONF_FILE. Copy scripts/staging.conf.example and fill in instance details." >&2
  exit 1
fi

# shellcheck source=/dev/null
source "$CONF_FILE"

: "${STAGING_INSTANCE_ID:?Set STAGING_INSTANCE_ID in scripts/staging.conf}"
: "${AWS_REGION:?Set AWS_REGION in scripts/staging.conf}"

echo "Starting staging instance $STAGING_INSTANCE_ID in $AWS_REGION..."
aws ec2 start-instances --instance-ids "$STAGING_INSTANCE_ID" --region "$AWS_REGION" >/dev/null
aws ec2 wait instance-status-ok --instance-ids "$STAGING_INSTANCE_ID" --region "$AWS_REGION"

PUBLIC_IP="$(aws ec2 describe-instances \
  --instance-ids "$STAGING_INSTANCE_ID" \
  --region "$AWS_REGION" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)"

echo "Staging instance is ready."
echo "Public IP: $PUBLIC_IP"
echo "SSH Host: ${STAGING_SSH_HOST:-"set STAGING_SSH_HOST to show dns"}"

