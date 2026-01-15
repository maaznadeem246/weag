#!/bin/bash

# Integration test script for Green Agent + Test Purple Agent
# Implements T103: Test end-to-end evaluation flow
#
# Tests:
# 1. Green Agent startup
# 2. Test Purple Agent evaluation request
# 3. MCP connection establishment
# 4. Task completion
# 5. Artifact submission

set -e

echo "=========================================="
echo "Green Agent + Purple Agent Integration Test"
echo "=========================================="

# Configuration
GREEN_AGENT_PORT=9009
GREEN_AGENT_URL="http://localhost:${GREEN_AGENT_PORT}"
TASK_ID="miniwob.click-test"
BENCHMARK="miniwob"
TEST_TIMEOUT=120

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up...${NC}"
    
    # Kill Green Agent
    if [ ! -z "$GREEN_AGENT_PID" ]; then
        echo "Stopping Green Agent (PID: $GREEN_AGENT_PID)"
        kill $GREEN_AGENT_PID 2>/dev/null || true
        wait $GREEN_AGENT_PID 2>/dev/null || true
    fi
    
    # Kill Purple Agent
    if [ ! -z "$PURPLE_AGENT_PID" ]; then
        echo "Stopping Purple Agent (PID: $PURPLE_AGENT_PID)"
        kill $PURPLE_AGENT_PID 2>/dev/null || true
        wait $PURPLE_AGENT_PID 2>/dev/null || true
    fi
    
    echo -e "${GREEN}Cleanup complete${NC}"
}

trap cleanup EXIT

# Step 1: Start Green Agent
echo -e "\n${YELLOW}[1/5] Starting Green Agent...${NC}"
python -m src.green_agent.main > logs/green_agent_test.log 2>&1 &
GREEN_AGENT_PID=$!

echo "Green Agent PID: $GREEN_AGENT_PID"
echo "Waiting for Green Agent to start..."

# Wait for Green Agent to be ready
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s "${GREEN_AGENT_URL}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Green Agent is ready${NC}"
        break
    fi
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    
    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo -e "${RED}✗ Green Agent failed to start${NC}"
        exit 1
    fi
    
    sleep 1
done

# Step 2: Verify Green Agent health
echo -e "\n${YELLOW}[2/5] Verifying Green Agent health...${NC}"
HEALTH_RESPONSE=$(curl -s "${GREEN_AGENT_URL}/health")
echo "Health response: $HEALTH_RESPONSE"

if echo "$HEALTH_RESPONSE" | grep -q '"status":"healthy"'; then
    echo -e "${GREEN}✓ Green Agent is healthy${NC}"
else
    echo -e "${RED}✗ Green Agent health check failed${NC}"
    exit 1
fi

# Step 3: Submit evaluation request via Purple Agent
echo -e "\n${YELLOW}[3/5] Submitting evaluation request via Purple Agent...${NC}"

# Set environment variables for Purple Agent
export GREEN_AGENT_URL="${GREEN_AGENT_URL}"
export GEMINI_API_KEY="${GEMINI_API_KEY:-test-key-placeholder}"

# Run Purple Agent in background
python -m tests.purple_agent.main \
    --task-id "${TASK_ID}" \
    --benchmark "${BENCHMARK}" \
    --timeout ${TEST_TIMEOUT} \
    > logs/purple_agent_test.log 2>&1 &

PURPLE_AGENT_PID=$!
echo "Purple Agent PID: $PURPLE_AGENT_PID"

# Step 4: Monitor Purple Agent execution
echo -e "\n${YELLOW}[4/5] Monitoring Purple Agent execution...${NC}"

# Wait for Purple Agent to complete (with timeout)
ELAPSED=0
while [ $ELAPSED -lt $TEST_TIMEOUT ]; do
    # Check if Purple Agent is still running
    if ! kill -0 $PURPLE_AGENT_PID 2>/dev/null; then
        # Purple Agent completed
        wait $PURPLE_AGENT_PID
        PURPLE_EXIT_CODE=$?
        
        if [ $PURPLE_EXIT_CODE -eq 0 ]; then
            echo -e "${GREEN}✓ Purple Agent completed successfully${NC}"
            break
        else
            echo -e "${RED}✗ Purple Agent failed (exit code: $PURPLE_EXIT_CODE)${NC}"
            echo "Purple Agent logs:"
            tail -n 50 logs/purple_agent_test.log
            exit 1
        fi
    fi
    
    sleep 1
    ELAPSED=$((ELAPSED + 1))
    
    # Show progress every 10 seconds
    if [ $((ELAPSED % 10)) -eq 0 ]; then
        echo "Still running... (${ELAPSED}s elapsed)"
    fi
done

if [ $ELAPSED -ge $TEST_TIMEOUT ]; then
    echo -e "${RED}✗ Purple Agent timed out${NC}"
    exit 1
fi

# Step 5: Verify results
echo -e "\n${YELLOW}[5/5] Verifying results...${NC}"

# Check Purple Agent logs for success indicators
if grep -q "Evaluation complete" logs/purple_agent_test.log; then
    echo -e "${GREEN}✓ Evaluation completed${NC}"
else
    echo -e "${RED}✗ Evaluation did not complete${NC}"
    exit 1
fi

if grep -q "Submitting evaluation artifact" logs/purple_agent_test.log; then
    echo -e "${GREEN}✓ Artifact submitted${NC}"
else
    echo -e "${RED}✗ Artifact was not submitted${NC}"
    exit 1
fi

# Check Green Agent logs for auto-initialization
if grep -q "Auto-initializing environment" logs/green_agent_test.log; then
    echo -e "${GREEN}✓ MCP environment auto-initialized by Green Agent${NC}"
else
    echo -e "${RED}✗ MCP environment was not auto-initialized${NC}"
    exit 1
fi

# Final summary
echo -e "\n=========================================="
echo -e "${GREEN}✓ Integration Test PASSED${NC}"
echo -e "=========================================="
echo ""
echo "Test Summary:"
echo "  - Green Agent: Started and healthy"
echo "  - Purple Agent: Completed evaluation"
echo "  - MCP Connection: Established and used"
echo "  - Task: ${TASK_ID}"
echo "  - Benchmark: ${BENCHMARK}"
echo "  - Artifact: Submitted successfully"
echo ""
echo "Logs:"
echo "  - Green Agent: logs/green_agent_test.log"
echo "  - Purple Agent: logs/purple_agent_test.log"

exit 0
