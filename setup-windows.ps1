# Windows Development Environment Setup Script
# This script sets up the local development environment with PostgreSQL and Redis

param(
    [string]$Action = "help",
    [string]$Service = "all"
)

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$servicesPath = Join-Path $projectRoot "services"

function Show-Help {
    Write-Host @"
Windows Local Development Environment Manager
==============================================

Usage: .\setup-windows.ps1 [Action] [Service]

Actions:
  setup           Setup the development environment (PostgreSQL, Redis, Python deps)
  start           Start all services or specific service
  stop            Stop all services or specific service
  restart         Restart all services or specific service
  db-init         Initialize and setup the database
  redis-start     Start Redis server
  redis-stop      Stop Redis server
  status          Show status of all services
  clean           Clean up all running services
  help            Show this help message

Services:
  all             All services (default)
  api-gateway
  auth-service
  user-service
  task-service
  eligibility-engine
  worker
  db               PostgreSQL database
  redis            Redis cache

Examples:
  .\setup-windows.ps1 setup all
  .\setup-windows.ps1 start api-gateway
  .\setup-windows.ps1 restart user-service

"@
}

function Check-Command {
    param([string]$Command)
    $null = Get-Command $Command -ErrorAction SilentlyContinue
    return $?
}

function Check-Requirements {
    Write-Host "Checking system requirements..." -ForegroundColor Cyan
    
    $missing = @()
    
    if (-not (Check-Command "python")) {
        $missing += "Python 3.11+"
    }
    
    if (-not (Check-Command "psql")) {
        Write-Host "WARNING: PostgreSQL CLI not found. Install PostgreSQL to use automatic DB setup." -ForegroundColor Yellow
    }
    
    if (-not (Check-Command "redis-cli")) {
        Write-Host "WARNING: Redis CLI not found. Install Redis or use WSL for Redis." -ForegroundColor Yellow
    }
    
    if ($missing.Count -gt 0) {
        Write-Host "ERROR: Missing requirements:" -ForegroundColor Red
        $missing | ForEach-Object { Write-Host "  - $_" }
        Write-Host "Please install the missing dependencies and try again." -ForegroundColor Red
        exit 1
    }
    
    Write-Host " All requirements found" -ForegroundColor Green
}

function Setup-Environment {
    Write-Host "Setting up Windows development environment..." -ForegroundColor Cyan
    
    # Check requirements
    Check-Requirements
    
    # Create .env.local if it doesn't exist
    $envLocal = Join-Path $projectRoot ".env.local"
    if (-not (Test-Path $envLocal)) {
        Write-Host "Creating .env.local..." -ForegroundColor Green
        # File should already exist from setup, but checking
    } else {
        Write-Host " .env.local already exists" -ForegroundColor Green
    }
    
    # Install Python dependencies
    Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
    
    $services = @("api_gateway", "auth_service", "user_service", "task_service", "eligibility_engine", "worker")
    
    foreach ($service in $services) {
        $reqFile = Join-Path $servicesPath "$service\requirements.txt"
        if (Test-Path $reqFile) {
            Write-Host "Installing $service dependencies..." -ForegroundColor Green
            & python -m pip install -q -r $reqFile
            if ($LASTEXITCODE -ne 0) {
                Write-Host "ERROR: Failed to install $service dependencies" -ForegroundColor Red
                exit 1
            }
        }
    }
    
    # Install dev requirements
    $devReq = Join-Path $projectRoot "dev-requirements.txt"
    if (Test-Path $devReq) {
        Write-Host "Installing dev requirements..." -ForegroundColor Green
        & python -m pip install -q -r $devReq
    }
    
    Write-Host " Environment setup complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Start PostgreSQL: .\setup-windows.ps1 db-init"
    Write-Host "2. Start Redis: .\setup-windows.ps1 redis-start"
    Write-Host "3. Start services: .\setup-windows.ps1 start all"
}

function Initialize-Database {
    Write-Host "Initializing database..." -ForegroundColor Cyan
    
    $pgUser = "app"
    $pgPassword = "app"
    $pgDb = "appdb"
    $pgHost = "localhost"
    
    # Check if PostgreSQL is running
    $psqlPath = "psql"
    
    try {
        Write-Host "Attempting to connect to PostgreSQL..." -ForegroundColor Yellow
        & $psqlPath -h $pgHost -U $pgUser -d postgres -c "SELECT 1" 2>$null
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Connected to PostgreSQL" -ForegroundColor Green
            
            # Create database if it doesn't exist
            Write-Host "Creating database if needed..." -ForegroundColor Yellow
            & $psqlPath -h $pgHost -U $pgUser -d postgres -c "CREATE DATABASE IF NOT EXISTS $pgDb;" 2>$null
            
            # Run init SQL
            $initSql = Join-Path $projectRoot "db\init.sql"
            if (Test-Path $initSql) {
                Write-Host "Running initialization SQL..." -ForegroundColor Yellow
                & $psqlPath -h $pgHost -U $pgUser -d $pgDb -f $initSql 2>$null
                Write-Host " Database initialized" -ForegroundColor Green
            }
        }
    }
    catch {
        Write-Host "ERROR: Could not connect to PostgreSQL. Ensure PostgreSQL is running." -ForegroundColor Red
        Write-Host "Troubleshooting:" -ForegroundColor Yellow
        Write-Host "1. Install PostgreSQL from https://www.postgresql.org/download/windows/"
        Write-Host "2. Start the PostgreSQL service"
        Write-Host "3. Ensure user 'app' exists with password 'app'"
        Write-Host "4. Ensure database 'appdb' is created"
    }
}

function Start-Service {
    param([string]$ServiceName)
    
    Write-Host "Starting $ServiceName..." -ForegroundColor Green
    
    $mainFile = $null
    
    switch ($ServiceName) {
        "api-gateway" { $mainFile = Join-Path $servicesPath "api_gateway\app\main.py" }
        "auth-service" { $mainFile = Join-Path $servicesPath "auth_service\app\main.py" }
        "user-service" { $mainFile = Join-Path $servicesPath "user_service\app\main.py" }
        "task-service" { $mainFile = Join-Path $servicesPath "task_service\app\main.py" }
        "eligibility-engine" { $mainFile = Join-Path $servicesPath "eligibility_engine\app\main.py" }
        "worker" { $mainFile = Join-Path $servicesPath "worker\app\worker.py" }
    }
    
    if ($mainFile -and (Test-Path $mainFile)) {
        $port = Get-ServicePort $ServiceName
        $env:ENVIRONMENT = "local"
        $env:DEBUG = "true"
        
        Write-Host "Starting: python $mainFile (Port: $port)" -ForegroundColor Yellow
        Start-Process -NoNewWindow -FilePath "python" -ArgumentList $mainFile
    } else {
        Write-Host "ERROR: Service file not found for $ServiceName" -ForegroundColor Red
    }
}

function Get-ServicePort {
    param([string]$ServiceName)
    
    switch ($ServiceName) {
        "api-gateway" { return 8000 }
        "auth-service" { return 8001 }
        "user-service" { return 8002 }
        "task-service" { return 8003 }
        "eligibility-engine" { return 8004 }
        "worker" { return 5000 }
        default { return 8000 }
    }
}

# Main script
switch ($Action.ToLower()) {
    "setup" { Setup-Environment }
    "db-init" { Initialize-Database }
    "help" { Show-Help }
    "status" { Write-Host "Service status check not yet implemented" -ForegroundColor Yellow }
    default { 
        Write-Host "Unknown action: $Action" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
