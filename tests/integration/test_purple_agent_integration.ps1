# Integration test script for Green Agent + Test Purple Agent
# Implements T103: Test end-to-end evaluation flow
#
# Tests:
# 1. Green Agent startup
# 2. Test Purple Agent evaluation request
# 3. MCP connection establishment
# 4. Task completion
# 5. Artifact submission

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Green Agent + Purple Agent Integration Test" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# Configuration
$GREEN_AGENT_PORT = 9009
$GREEN_AGENT_URL = "http://localhost:$GREEN_AGENT_PORT"
$TASK_ID = "miniwob.click-test"
$BENCHMARK = "miniwob"
$TEST_TIMEOUT = 120

# Process tracking
$GREEN_AGENT_PROCESS = $null
$PURPLE_AGENT_PROCESS = $null

# Cleanup function
function Cleanup {
    Write-Host "`nCleaning up..." -ForegroundColor Yellow
    
    if ($GREEN_AGENT_PROCESS) {
        Write-Host "Stopping Green Agent (PID: $($GREEN_AGENT_PROCESS.Id))"
        Stop-Process -Id $GREEN_AGENT_PROCESS.Id -Force -ErrorAction SilentlyContinue
    }
    
    if ($PURPLE_AGENT_PROCESS) {
        Write-Host "Stopping Purple Agent (PID: $($PURPLE_AGENT_PROCESS.Id))"
        Stop-Process -Id $PURPLE_AGENT_PROCESS.Id -Force -ErrorAction SilentlyContinue
    }
    
    Write-Host "Cleanup complete" -ForegroundColor Green
}

# Register cleanup
Register-EngineEvent PowerShell.Exiting -Action { Cleanup }

try {
    # Step 1: Start Green Agent
    Write-Host "`n[1/5] Starting Green Agent..." -ForegroundColor Yellow
    
    $GREEN_AGENT_PROCESS = Start-Process -FilePath "python" -ArgumentList "-m", "src.green_agent.main" `
        -RedirectStandardOutput "logs/green_agent_test.log" `
        -RedirectStandardError "logs/green_agent_test_err.log" `
        -NoNewWindow -PassThru
    
    Write-Host "Green Agent PID: $($GREEN_AGENT_PROCESS.Id)"
    Write-Host "Waiting for Green Agent to start..."
    
    # Wait for Green Agent to be ready
    $MAX_RETRIES = 30
    $RETRY_COUNT = 0
    $IS_READY = $false
    
    while ($RETRY_COUNT -lt $MAX_RETRIES) {
        try {
            $response = Invoke-WebRequest -Uri "$GREEN_AGENT_URL/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host "✓ Green Agent is ready" -ForegroundColor Green
                $IS_READY = $true
                break
            }
        } catch {
            # Ignore errors during startup
        }
        
        $RETRY_COUNT++
        Start-Sleep -Seconds 1
    }
    
    if (-not $IS_READY) {
        Write-Host "✗ Green Agent failed to start" -ForegroundColor Red
        exit 1
    }
    
    # Step 2: Verify Green Agent health
    Write-Host "`n[2/5] Verifying Green Agent health..." -ForegroundColor Yellow
    
    $healthResponse = Invoke-RestMethod -Uri "$GREEN_AGENT_URL/health"
    Write-Host "Health response: $($healthResponse | ConvertTo-Json -Compress)"
    
    if ($healthResponse.status -eq "healthy") {
        Write-Host "✓ Green Agent is healthy" -ForegroundColor Green
    } else {
        Write-Host "✗ Green Agent health check failed" -ForegroundColor Red
        exit 1
    }
    
    # Step 3: Submit evaluation request via Purple Agent
    Write-Host "`n[3/5] Submitting evaluation request via Purple Agent..." -ForegroundColor Yellow
    
    # Set environment variables for Purple Agent
    $env:GREEN_AGENT_URL = $GREEN_AGENT_URL
    if (-not $env:GEMINI_API_KEY) {
        $env:GEMINI_API_KEY = "test-key-placeholder"
    }
    
    # Run Purple Agent
    $PURPLE_AGENT_PROCESS = Start-Process -FilePath "python" -ArgumentList `
        "-m", "tests.purple_agent.main", `
        "--task-id", $TASK_ID, `
        "--benchmark", $BENCHMARK, `
        "--timeout", $TEST_TIMEOUT `
        -RedirectStandardOutput "logs/purple_agent_test.log" `
        -RedirectStandardError "logs/purple_agent_test_err.log" `
        -NoNewWindow -PassThru
    
    Write-Host "Purple Agent PID: $($PURPLE_AGENT_PROCESS.Id)"
    
    # Step 4: Monitor Purple Agent execution
    Write-Host "`n[4/5] Monitoring Purple Agent execution..." -ForegroundColor Yellow
    
    $ELAPSED = 0
    $COMPLETED = $false
    
    while ($ELAPSED -lt $TEST_TIMEOUT) {
        if ($PURPLE_AGENT_PROCESS.HasExited) {
            $EXIT_CODE = $PURPLE_AGENT_PROCESS.ExitCode
            
            if ($EXIT_CODE -eq 0) {
                Write-Host "✓ Purple Agent completed successfully" -ForegroundColor Green
                $COMPLETED = $true
                break
            } else {
                Write-Host "✗ Purple Agent failed (exit code: $EXIT_CODE)" -ForegroundColor Red
                Write-Host "Purple Agent logs:"
                Get-Content "logs/purple_agent_test.log" -Tail 50
                exit 1
            }
        }
        
        Start-Sleep -Seconds 1
        $ELAPSED++
        
        # Show progress every 10 seconds
        if (($ELAPSED % 10) -eq 0) {
            Write-Host "Still running... (${ELAPSED}s elapsed)"
        }
    }
    
    if (-not $COMPLETED) {
        Write-Host "✗ Purple Agent timed out" -ForegroundColor Red
        exit 1
    }
    
    # Step 5: Verify results
    Write-Host "`n[5/5] Verifying results..." -ForegroundColor Yellow
    
    # Check Purple Agent logs for success indicators
    $purpleLog = Get-Content "logs/purple_agent_test.log" -Raw
    
    if ($purpleLog -match "Evaluation complete") {
        Write-Host "✓ Evaluation completed" -ForegroundColor Green
    } else {
        Write-Host "✗ Evaluation did not complete" -ForegroundColor Red
        exit 1
    }
    
    if ($purpleLog -match "Submitting evaluation artifact") {
        Write-Host "✓ Artifact submitted" -ForegroundColor Green
    } else {
        Write-Host "✗ Artifact was not submitted" -ForegroundColor Red
        exit 1
    }
    
    # Check Green Agent logs for auto-initialization
    $greenLog = Get-Content "logs/green_agent_test.log" -Raw
    
    if ($greenLog -match "Auto-initializing environment") {
        Write-Host "✓ MCP environment auto-initialized by Green Agent" -ForegroundColor Green
    } else {
        Write-Host "✗ MCP environment was not auto-initialized" -ForegroundColor Red
        exit 1
    }
    
    # Final summary
    Write-Host "`n==========================================" -ForegroundColor Cyan
    Write-Host "✓ Integration Test PASSED" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Test Summary:"
    Write-Host "  - Green Agent: Started and healthy"
    Write-Host "  - Purple Agent: Completed evaluation"
    Write-Host "  - MCP Connection: Established and used"
    Write-Host "  - Task: $TASK_ID"
    Write-Host "  - Benchmark: $BENCHMARK"
    Write-Host "  - Artifact: Submitted successfully"
    Write-Host ""
    Write-Host "Logs:"
    Write-Host "  - Green Agent: logs/green_agent_test.log"
    Write-Host "  - Purple Agent: logs/purple_agent_test.log"
    
    exit 0
    
} finally {
    Cleanup
}
