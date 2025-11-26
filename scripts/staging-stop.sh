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

echo "Stopping staging instance $STAGING_INSTANCE_ID..."
aws ec2 stop-instances --instance-ids "$STAGING_INSTANCE_ID" --region "$AWS_REGION" >/dev/null
aws ec2 wait instance-stopped --instance-ids "$STAGING_INSTANCE_ID" --region "$AWS_REGION"

echo "Staging instance stopped. Remember to clean up any temporary DNS overrides."

