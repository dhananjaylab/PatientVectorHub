# PowerShell script to reorganize tests by service
# Usage: .\reorganize_tests.ps1

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "📁 Creating service-level test directories..." -ForegroundColor Green

$services = @(
    "api-gateway"
    "ingestion"
    "vector-store"
    "rag-engine"
)

foreach ($service in $services) {
    $testDir = Join-Path $repoRoot $service tests
    New-Item -ItemType Directory -Path (Join-Path $testDir unit) -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $testDir integration) -Force | Out-Null
    Write-Host "  ✓ Created $service/tests/{unit,integration}" -ForegroundColor Cyan
}

# Create shared tests directory
New-Item -ItemType Directory -Path (Join-Path $repoRoot tests shared) -Force | Out-Null
Write-Host "  ✓ Created tests/shared" -ForegroundColor Cyan

# Create embedding-server tests
New-Item -ItemType Directory -Path (Join-Path $repoRoot embedding-server tests unit) -Force | Out-Null
Write-Host "  ✓ Created embedding-server/tests/unit" -ForegroundColor Cyan

Write-Host "`n📋 Test file mapping completed." -ForegroundColor Green
Write-Host "Next: Run the Python migration script to move files and update imports" -ForegroundColor Yellow
