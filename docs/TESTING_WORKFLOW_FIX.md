# Testing the ECS Task Definition Update Fix

This document explains how to verify that the workflow fix for handling missing task definitions works correctly.

## Quick Test (Local)

Run the test script that simulates the workflow logic:

```bash
./scripts/test_workflow_task_update.sh
```

This script:
- ✅ Simulates missing task definitions (4 out of 6)
- ✅ Tests the existence check logic
- ✅ Validates that the workflow continues even when some tasks don't exist
- ✅ Verifies correct output formatting

**Expected Output:**
- 2 task definitions updated (reddit-scraper, daily-status)
- 4 task definitions skipped (sentiment-analysis, stock-price-collector, send-daily-emails, historical-backfill)
- Test should PASS ✅

## Testing Options

### 1. **Local Script Test** (Recommended First Step)
```bash
./scripts/test_workflow_task_update.sh
```

**Pros:**
- No AWS credentials needed
- Fast execution
- Validates the core logic
- Can run multiple times

**Cons:**
- Doesn't test actual AWS API calls
- Uses mocked AWS CLI

### 2. **Workflow Dry-Run Mode** (Best for Real-World Testing)

The workflow supports dry-run mode via manual dispatch:

1. Go to GitHub Actions → Deploy ECS Jobs workflow
2. Click "Run workflow"
3. Select:
   - Environment: `production` (or `staging`)
   - **Dry run**: `true` ✅
4. Click "Run workflow"

**What it tests:**
- ✅ Builds Docker image
- ✅ Validates workflow syntax
- ✅ Tests change detection logic
- ⚠️ Won't push to ECR or update task definitions (by design)

**Pros:**
- Tests full workflow without making changes
- Validates GitHub Actions environment
- Safe to run anytime

**Cons:**
- Doesn't test actual AWS API calls
- Requires GitHub Actions access

### 3. **Manual Workflow Trigger** (Full Test)

**⚠️ Warning:** This will actually update task definitions in AWS!

1. Go to GitHub Actions → Deploy ECS Jobs workflow
2. Click "Run workflow"
3. Select:
   - Environment: `staging` (safer than production)
   - Dry run: `false`
4. Click "Run workflow"
5. Monitor the logs, especially the "Update ECS task definitions" step

**What to look for:**
- ✅ Task definitions that exist should be updated successfully
- ✅ Task definitions that don't exist should be skipped with message: "Task definition X does not exist yet (will be created by Terraform)"
- ✅ Workflow should complete successfully even if some tasks don't exist
- ✅ Deployment summary should show both updated and skipped tasks

**Pros:**
- Tests real AWS API calls
- Validates end-to-end behavior
- Confirms fix works in production environment

**Cons:**
- Requires AWS credentials configured in GitHub Secrets
- Makes actual changes to AWS resources
- May incur AWS costs

### 4. **Local AWS CLI Test** (If You Have AWS Access)

Test the actual AWS commands locally:

```bash
# Set your AWS credentials
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="us-east-1"

# Test checking for a non-existent task definition
aws ecs describe-task-definition \
  --task-definition market-pulse-test-nonexistent \
  --query taskDefinition 2>&1 || echo "✅ Correctly failed for non-existent task"

# Test checking for an existing task definition (if you have one)
aws ecs describe-task-definition \
  --task-definition market-pulse-reddit-scraper \
  --query taskDefinition 2>&1 && echo "✅ Found existing task definition"
```

**Pros:**
- Tests actual AWS API behavior
- Validates error handling
- No workflow overhead

**Cons:**
- Requires AWS credentials
- Need to know which tasks exist/don't exist

### 5. **Validate YAML Syntax**

Check the workflow file syntax:

```bash
# Using Python's yaml module (if available)
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-ecs-jobs.yml'))" && echo "✅ YAML syntax valid"

# Or use online validators:
# - https://www.yamllint.com/
# - VS Code YAML extension
```

## Expected Behavior After Fix

### Before Fix (❌ Failed)
```
Updating market-pulse-daily-status...
An error occurred (ClientException) when calling the DescribeTaskDefinition operation: Unable to describe task definition.
Error: Process completed with exit code 254.
```

### After Fix (✅ Works)
```
Checking market-pulse-daily-status...
Updating market-pulse-daily-status...
✅ Successfully updated market-pulse-daily-status

Checking market-pulse-stock-price-collector...
ℹ️  Task definition market-pulse-stock-price-collector does not exist yet (will be created by Terraform)

✅ Updated all ECS task definitions
```

## Validation Checklist

- [ ] Local test script passes (`./scripts/test_workflow_task_update.sh`)
- [ ] Workflow YAML syntax is valid
- [ ] Dry-run mode completes successfully
- [ ] Manual trigger shows correct behavior for missing tasks
- [ ] Deployment summary shows both updated and skipped tasks
- [ ] Workflow doesn't fail when some tasks don't exist

## Troubleshooting

### Test Script Fails
- Check if `jq` is installed: `which jq`
- Ensure script is executable: `chmod +x scripts/test_workflow_task_update.sh`
- Check bash version: `bash --version` (should be 4.0+)

### Workflow Still Fails
- Check AWS credentials in GitHub Secrets
- Verify task definition names match exactly
- Check AWS region is correct (`us-east-1`)
- Review workflow logs for specific error messages

### Tasks Not Being Skipped
- Verify the `2>/dev/null` redirect is present in the `describe-task-definition` command
- Check that the `if` statement properly handles the exit code
- Ensure `|| true` is present after each `update_task_definition` call

## Related Files

- Workflow: `.github/workflows/deploy-ecs-jobs.yml`
- Test Script: `scripts/test_workflow_task_update.sh`
- Terraform: `infrastructure/terraform/ecs.tf` (creates task definitions)


