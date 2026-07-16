# Windows PowerShell script for development tasks
# Usage: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('dev', 'dev-lite', 'stop', 'logs', 'migrate', 'migration', 'seed', 'setup-vector-stores', 'kafka-topics', 'vault-init', 'test-unit', 'test-integration', 'clean')]
    [string]$Task
)

$ErrorActionPreference = "Stop"

function Write-Status {
    param([string]$Message)
    Write-Host "▶ $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
}

function Write-Wait {
    param([string]$Message)
    Write-Host "⏳ $Message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
    exit 1
}

function Wait-Healthy {
    $services = @('pvh-postgres', 'pvh-redis', 'pvh-weaviate', 'pvh-vault', 'pvh-kafka')
    
    foreach ($svc in $services) {
        Write-Host "  Checking $svc..."
        $healthy = $false
        
        for ($i = 1; $i -le 18; $i++) {
            try {
                $status = & docker inspect --format='{{.State.Health.Status}}' $svc 2>$null
                if ($status -eq "healthy") {
                    Write-Host "  ✓ $svc"
                    $healthy = $true
                    break
                }
            }
            catch {
                # Container may not be running yet
            }
            
            if ($i -eq 18 -and -not $healthy) {
                Write-Error-Custom "$svc not healthy after 90s"
            }
            
            if (-not $healthy) {
                Start-Sleep -Seconds 5
            }
        }
    }
}

function Start-Dev {
    Write-Status "Starting full PatientVectorHub stack..."
    & docker compose up -d
    Write-Wait "Waiting for services to be healthy (up to 90s)..."
    Start-Sleep -Seconds 10
    Wait-Healthy
    Write-Host ""
    Write-Status "All services healthy. Running setup..."
    Invoke-Vault-Init
    Invoke-Migrate
    Invoke-Kafka-Topics
    Invoke-Setup-Vector-Stores
    Invoke-Seed
    
    Write-Host ""
    Write-Host "  ┌─────────────────────────────────────────────────┐"
    Write-Host "  │  PatientVectorHub — Local Stack Ready            │"
    Write-Host "  │                                                  │"
    Write-Host "  │  FastAPI  → http://localhost:8000/health         │"
    Write-Host "  │  Weaviate → http://localhost:8080                │"
    Write-Host "  │  Qdrant   → http://localhost:6333                │"
    Write-Host "  │  Vault    → http://localhost:8200                │"
    Write-Host "  │  Keycloak → http://localhost:8443                │"
    Write-Host "  │  Kafka    → localhost:9092                       │"
    Write-Host "  │  Redis    → localhost:6379                       │"
    Write-Host "  │  Embed    → http://localhost:8001                │"
    Write-Host "  └─────────────────────────────────────────────────┘"
    Write-Host ""
}

function Start-Dev-Lite {
    Write-Status "Starting minimal stack (Postgres, Redis, Weaviate, Kafka, Vault)..."
    & docker compose up -d postgres redis weaviate kafka vault
    Write-Wait "Waiting for services..."
    Start-Sleep -Seconds 8
    Invoke-Vault-Init
    Invoke-Migrate
    Invoke-Kafka-Topics
    Invoke-Seed
    Write-Success "Lite stack ready (Keycloak + Qdrant + Embedding skipped)"
}

function Stop-Stack {
    & docker compose down
    Write-Success "All containers stopped"
}

function Clean-Stack {
    & docker compose down -v --remove-orphans
    Write-Success "Containers, networks, and volumes removed"
}

function Show-Logs {
    & docker compose logs -f --tail=50
}

function Invoke-Migrate {
    Write-Status "Running Alembic upgrade head"
    Push-Location api-gateway
    & python -m alembic upgrade head
    Pop-Location
    Write-Success "Migrations applied"
}

function Invoke-Migration {
    $message = Read-Host "Migration message"
    if ([string]::IsNullOrWhiteSpace($message)) {
        Write-Error-Custom "Migration message cannot be empty"
    }
    Push-Location api-gateway
    & python -m alembic revision --autogenerate -m "$message"
    Pop-Location
}

function Invoke-Seed {
    Write-Status "Seeding synthetic test data..."
    & python scripts\seed_data.py
    Write-Success "Seed complete: 2 tenants, 4 users each, 1000 patients each"
}

function Invoke-Setup-Vector-Stores {
    Write-Status "Creating Weaviate + Qdrant schemas for all tenants..."
    & python scripts\setup_weaviate_schema.py
    & python scripts\setup_qdrant_schema.py
    Write-Success "Vector store schemas created"
}

function Invoke-Kafka-Topics {
    Write-Status "Creating Kafka topics..."
    & python scripts\create_kafka_topics.py
    Write-Success "Kafka topics created"
}

function Invoke-Vault-Init {
    Write-Status "Initialising Vault dev secrets..."
    # Try to use bash from Git for Windows if available
    $bashPath = "C:\Program Files\Git\bin\bash.exe"
    if (Test-Path $bashPath) {
        & $bashPath scripts\vault_init.sh
        Write-Success "Vault initialised"
    }
    else {
        Write-Host "Note: vault_init.sh requires bash. Install Git for Windows or run:" -ForegroundColor Yellow
        Write-Host "  bash scripts/vault_init.sh" -ForegroundColor Yellow
        Write-Success "Vault initialised (manual)"
    }
}

function Invoke-Tests-Unit {
    Write-Status "Running unit tests..."
    & pytest tests\unit -v --tb=short
    Write-Success "Unit tests passed"
}

function Invoke-Tests-Integration {
    Write-Status "Running integration tests (requires running stack)..."
    & pytest tests\integration -v --tb=short -m integration
    Write-Success "Integration tests passed"
}

# Main dispatcher
switch ($Task) {
    'dev' { Start-Dev }
    'dev-lite' { Start-Dev-Lite }
    'stop' { Stop-Stack }
    'clean' { Clean-Stack }
    'logs' { Show-Logs }
    'migrate' { Invoke-Migrate }
    'migration' { Invoke-Migration }
    'seed' { Invoke-Seed }
    'setup-vector-stores' { Invoke-Setup-Vector-Stores }
    'kafka-topics' { Invoke-Kafka-Topics }
    'vault-init' { Invoke-Vault-Init }
    'test-unit' { Invoke-Tests-Unit }
    'test-integration' { Invoke-Tests-Integration }
    default { Write-Error-Custom "Unknown task: $Task" }
}
