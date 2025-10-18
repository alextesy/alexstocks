#!/bin/bash
set -e

echo "🔍 Validating ECS Migration Setup"
echo "=================================="
echo ""

ERRORS=0
WARNINGS=0

# Function to check file exists
check_file() {
    local file=$1
    local desc=$2
    if [ -f "$file" ]; then
        echo "✅ $desc"
    else
        echo "❌ $desc (MISSING)"
        ((ERRORS++))
    fi
}

# Function to check directory exists
check_dir() {
    local dir=$1
    local desc=$2
    if [ -d "$dir" ]; then
        echo "✅ $desc"
    else
        echo "❌ $desc (MISSING)"
        ((ERRORS++))
    fi
}

# Function to check command exists
check_command() {
    local cmd=$1
    local desc=$2
    if command -v "$cmd" &> /dev/null; then
        echo "✅ $desc ($(command -v $cmd))"
    else
        echo "⚠️  $desc (NOT FOUND)"
        ((WARNINGS++))
    fi
}

echo "1. Checking Prerequisites"
echo "-------------------------"
check_command "aws" "AWS CLI"
check_command "terraform" "Terraform"
check_command "docker" "Docker"
echo ""

echo "2. Checking Job Files"
echo "---------------------"
check_dir "jobs" "Jobs directory"
check_file "jobs/Dockerfile" "Jobs Dockerfile"
check_file "jobs/pyproject.toml" "Jobs pyproject.toml"
check_file "jobs/README.md" "Jobs README"
check_dir "jobs/app" "Jobs app directory"
check_dir "jobs/ingest" "Jobs ingest directory"
echo ""

echo "3. Checking Infrastructure Files"
echo "---------------------------------"
check_dir "infrastructure/terraform" "Terraform directory"
check_file "infrastructure/terraform/main.tf" "Terraform main.tf"
check_file "infrastructure/terraform/variables.tf" "Terraform variables.tf"
check_file "infrastructure/terraform/ecr.tf" "Terraform ECR config"
check_file "infrastructure/terraform/ecs.tf" "Terraform ECS config"
check_file "infrastructure/terraform/iam.tf" "Terraform IAM config"
check_file "infrastructure/terraform/eventbridge.tf" "Terraform EventBridge config"
check_file "infrastructure/terraform/terraform.tfvars.example" "Terraform example config"
echo ""

echo "4. Checking Documentation"
echo "-------------------------"
check_file "docs/ECS_MIGRATION_GUIDE.md" "Migration guide"
check_file "docs/MIGRATION_CHECKLIST.md" "Migration checklist"
check_file "infrastructure/README.md" "Infrastructure README"
check_file "ECS_MIGRATION_SUMMARY.md" "Migration summary"
echo ""

echo "5. Checking CI/CD"
echo "-----------------"
check_file ".github/workflows/deploy-ecs-jobs.yml" "GitHub Actions workflow"
echo ""

echo "6. Checking Scripts"
echo "-------------------"
check_file "scripts/setup-aws-secrets.sh" "AWS secrets setup script"
if [ -f "scripts/setup-aws-secrets.sh" ]; then
    if [ -x "scripts/setup-aws-secrets.sh" ]; then
        echo "✅ Script is executable"
    else
        echo "⚠️  Script is not executable (run: chmod +x scripts/setup-aws-secrets.sh)"
        ((WARNINGS++))
    fi
fi
echo ""

echo "7. Checking Makefile Commands"
echo "------------------------------"
if grep -q "ecr-login:" Makefile; then
    echo "✅ ECS commands added to Makefile"
else
    echo "❌ ECS commands not found in Makefile"
    ((ERRORS++))
fi
echo ""

echo "8. Checking .gitignore"
echo "----------------------"
if grep -q "terraform.tfvars" .gitignore; then
    echo "✅ terraform.tfvars in .gitignore"
else
    echo "⚠️  terraform.tfvars not in .gitignore (may commit secrets)"
    ((WARNINGS++))
fi
echo ""

# Optional: Check AWS credentials
echo "9. Checking AWS Configuration (optional)"
echo "-----------------------------------------"
if aws sts get-caller-identity &> /dev/null; then
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    REGION=$(aws configure get region)
    echo "✅ AWS credentials configured"
    echo "   Account: $ACCOUNT_ID"
    echo "   Region: ${REGION:-us-east-1 (default)}"
else
    echo "⚠️  AWS credentials not configured (run: aws configure)"
    ((WARNINGS++))
fi
echo ""

# Summary
echo "=================================="
echo "📊 VALIDATION SUMMARY"
echo "=================================="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo "✅ All checks passed!"
    echo ""
    echo "Next steps:"
    echo "1. Run: ./scripts/setup-aws-secrets.sh"
    echo "2. Configure: infrastructure/terraform/terraform.tfvars"
    echo "3. Deploy: make tf-init && make tf-plan && make tf-apply"
    echo ""
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo "✅ Setup complete with $WARNINGS warnings"
    echo ""
    echo "Next steps:"
    echo "1. Address warnings above"
    echo "2. Run: ./scripts/setup-aws-secrets.sh"
    echo "3. Configure: infrastructure/terraform/terraform.tfvars"
    echo "4. Deploy: make tf-init && make tf-plan && make tf-apply"
    echo ""
    exit 0
else
    echo "❌ Setup incomplete: $ERRORS errors, $WARNINGS warnings"
    echo ""
    echo "Please fix the errors above before proceeding."
    echo ""
    exit 1
fi
