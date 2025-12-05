#!/bin/bash
# Test script to validate the ECS task definition update logic
# This simulates the workflow's task definition update step

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Mock AWS CLI function that simulates task definition existence
mock_aws_describe_task_definition() {
    local task_name=$1
    local output_file=$2
    
    # Simulate: some task definitions exist, some don't
    case "$task_name" in
        "market-pulse-reddit-scraper")
            echo '{"family":"market-pulse-reddit-scraper","containerDefinitions":[{"image":"old-image:tag"}]}' > "$output_file"
            return 0
            ;;
        "market-pulse-sentiment-analysis")
            # Simulate missing task definition
            return 1
            ;;
        "market-pulse-daily-status")
            echo '{"family":"market-pulse-daily-status","containerDefinitions":[{"image":"old-image:tag"}]}' > "$output_file"
            return 0
            ;;
        "market-pulse-stock-price-collector")
            # Simulate missing task definition
            return 1
            ;;
        "market-pulse-send-daily-emails")
            # Simulate missing task definition
            return 1
            ;;
        "market-pulse-historical-backfill")
            # Simulate missing task definition
            return 1
            ;;
        *)
            return 1
            ;;
    esac
}

# Mock AWS CLI function for registering task definition
mock_aws_register_task_definition() {
    local input_file=$1
    if [ -f "$input_file" ]; then
        echo "✅ Mock: Registered task definition from $input_file"
        return 0
    else
        echo "❌ Mock: Failed to register - file not found"
        return 1
    fi
}

# Test the update_task_definition function
test_update_task_definition() {
    local IMAGE_URI="test-registry/test-repo:test-tag"
    local UPDATED_TASKS=""
    local SKIPPED_TASKS=""
    
    # Helper function (same as in workflow)
    update_task_definition() {
        local TASK_NAME=$1
        local TASK_FILE=$2
        
        echo "Checking $TASK_NAME..."
        
        # Check if task definition exists (using mock)
        if mock_aws_describe_task_definition "$TASK_NAME" "$TASK_FILE.json" 2>/dev/null; then
            echo "Updating $TASK_NAME..."
            
            # Update image (simplified - just check if jq would work)
            if command -v jq &> /dev/null; then
                jq --arg IMAGE "$IMAGE_URI" \
                    '.containerDefinitions[0].image = $IMAGE | del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .compatibilities, .registeredAt, .registeredBy)' \
                    "$TASK_FILE.json" > "$TASK_FILE-updated.json"
            else
                # Fallback: just copy the file if jq not available
                cp "$TASK_FILE.json" "$TASK_FILE-updated.json"
            fi
            
            if mock_aws_register_task_definition "$TASK_FILE-updated.json"; then
                echo -e "${GREEN}✅ Successfully updated $TASK_NAME${NC}"
                UPDATED_TASKS="$UPDATED_TASKS\n- $TASK_NAME"
                return 0
            else
                echo -e "${YELLOW}⚠️  Failed to register updated task definition for $TASK_NAME${NC}"
                SKIPPED_TASKS="$SKIPPED_TASKS\n- $TASK_NAME (registration failed)"
                return 1
            fi
        else
            echo -e "${YELLOW}ℹ️  Task definition $TASK_NAME does not exist yet (will be created by Terraform)${NC}"
            SKIPPED_TASKS="$SKIPPED_TASKS\n- $TASK_NAME (does not exist)"
            return 0
        fi
    }
    
    # Test all task definitions
    echo "=========================================="
    echo "Testing ECS Task Definition Update Logic"
    echo "=========================================="
    echo ""
    
    update_task_definition "market-pulse-reddit-scraper" "task-def-reddit" || true
    update_task_definition "market-pulse-sentiment-analysis" "task-def-sentiment" || true
    update_task_definition "market-pulse-daily-status" "task-def-status" || true
    update_task_definition "market-pulse-stock-price-collector" "task-def-stock-price" || true
    update_task_definition "market-pulse-send-daily-emails" "task-def-send-emails" || true
    update_task_definition "market-pulse-historical-backfill" "task-def-historical-backfill" || true
    
    echo ""
    echo "=========================================="
    echo "Test Results Summary"
    echo "=========================================="
    
    if [ -n "$UPDATED_TASKS" ]; then
        echo -e "${GREEN}✅ Updated task definitions:${NC}"
        echo -e "$UPDATED_TASKS"
    else
        echo -e "${YELLOW}ℹ️  No task definitions were updated${NC}"
    fi
    
    if [ -n "$SKIPPED_TASKS" ]; then
        echo ""
        echo -e "${YELLOW}ℹ️  Skipped task definitions:${NC}"
        echo -e "$SKIPPED_TASKS"
    fi
    
    echo ""
    
    # Cleanup
    rm -f task-def-*.json
    
    # Validate test results
    local updated_count=$(echo -e "$UPDATED_TASKS" | grep -c "^-" || echo "0")
    local skipped_count=$(echo -e "$SKIPPED_TASKS" | grep -c "^-" || echo "0")
    
    echo "=========================================="
    echo "Validation"
    echo "=========================================="
    echo "Expected: 2 updated, 4 skipped"
    echo "Actual: $updated_count updated, $skipped_count skipped"
    
    if [ "$updated_count" -eq 2 ] && [ "$skipped_count" -eq 4 ]; then
        echo -e "${GREEN}✅ Test PASSED - Logic works correctly!${NC}"
        return 0
    else
        echo -e "${RED}❌ Test FAILED - Unexpected results${NC}"
        return 1
    fi
}

# Run the test
if test_update_task_definition; then
    exit 0
else
    exit 1
fi


