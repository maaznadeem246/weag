# Docker Local Testing - Quick Start Script
# Run: .\docker-test.ps1

param(
    [switch]$Build,
    [switch]$Start,
    [switch]$Stop,
    [switch]$Logs,
    [switch]$Restart,
    [switch]$Clean,
    [switch]$Help
)

$ComposeFile = "docker-compose.local.yml"

function Show-Help {
    Write-Host "Docker Local Testing - Quick Start Script" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\docker-test.ps1 [options]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Green
    Write-Host "  -Build    Build Docker images"
    Write-Host "  -Start    Start containers (builds if needed)"
    Write-Host "  -Stop     Stop containers"
    Write-Host "  -Logs     Follow container logs"
    Write-Host "  -Restart  Restart containers"
    Write-Host "  -Clean    Stop and remove containers, networks, volumes"
    Write-Host "  -Help     Show this help message"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  .\docker-test.ps1 -Build       # Build images"
    Write-Host "  .\docker-test.ps1 -Start       # Start containers"
    Write-Host "  .\docker-test.ps1 -Logs        # View logs"
    Write-Host "  .\docker-test.ps1 -Stop        # Stop containers"
    Write-Host ""
    Write-Host "After starting containers, run assessment:" -ForegroundColor Cyan
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  python kickstart_assessment.py"
}

function Build-Images {
    Write-Host "🔨 Building Docker images..." -ForegroundColor Cyan
    docker compose -f $ComposeFile build
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Images built successfully" -ForegroundColor Green
    } else {
        Write-Host "✗ Build failed" -ForegroundColor Red
        exit 1
    }
}

function Start-Containers {
    Write-Host "🚀 Starting containers..." -ForegroundColor Cyan
    docker compose -f $ComposeFile up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Containers started" -ForegroundColor Green
        Write-Host ""
        Write-Host "Waiting for health checks..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
        docker compose -f $ComposeFile ps
        Write-Host ""
        Write-Host "Test endpoints:" -ForegroundColor Cyan
        Write-Host "  Green Agent: http://localhost:9009/health" -ForegroundColor White
        Write-Host "  Purple Agent: http://localhost:9010/.well-known/agent-card.json" -ForegroundColor White
        Write-Host ""
        Write-Host "Run assessment:" -ForegroundColor Cyan
        Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor White
        Write-Host "  python kickstart_assessment.py" -ForegroundColor White
    } else {
        Write-Host "✗ Failed to start containers" -ForegroundColor Red
        exit 1
    }
}

function Stop-Containers {
    Write-Host "🛑 Stopping containers..." -ForegroundColor Cyan
    docker compose -f $ComposeFile stop
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Containers stopped" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to stop containers" -ForegroundColor Red
        exit 1
    }
}

function Show-Logs {
    Write-Host "📋 Following container logs (Ctrl+C to exit)..." -ForegroundColor Cyan
    docker compose -f $ComposeFile logs -f
}

function Restart-Containers {
    Write-Host "🔄 Restarting containers..." -ForegroundColor Cyan
    docker compose -f $ComposeFile restart
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Containers restarted" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to restart containers" -ForegroundColor Red
        exit 1
    }
}

function Clean-All {
    Write-Host "🧹 Cleaning up Docker resources..." -ForegroundColor Cyan
    docker compose -f $ComposeFile down -v
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Cleanup complete" -ForegroundColor Green
    } else {
        Write-Host "✗ Cleanup failed" -ForegroundColor Red
        exit 1
    }
}

# Main execution
if ($Help) {
    Show-Help
    exit 0
}

# Check if no parameters were provided
$hasParams = $Build -or $Start -or $Stop -or $Logs -or $Restart -or $Clean

if (-not $hasParams) {
    Show-Help
    exit 0
}

if ($Build) {
    Build-Images
}

if ($Start) {
    Start-Containers
}

if ($Logs) {
    Show-Logs
}

if ($Restart) {
    Restart-Containers
}

if ($Stop) {
    Stop-Containers
}

if ($Clean) {
    Clean-All
}
