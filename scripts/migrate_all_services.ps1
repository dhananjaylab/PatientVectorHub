# Migrate all remaining services at once
# Usage: .\migrate_all_services.ps1

$services = @(
    "ingestion",
    "vector-store",
    "rag-engine",
    "embedding-server"
)

Write-Host "🚀 Migrating all services..." -ForegroundColor Green
Write-Host ""

foreach ($service in $services) {
    $script = "scripts/copy_and_update_${service}_tests.py"
    
    if (Test-Path $script) {
        Write-Host "Migrating $service..." -ForegroundColor Cyan
        python $script
        Write-Host ""
    }
    else {
        Write-Host "⚠ Script not found: $script" -ForegroundColor Yellow
    }
}

Write-Host "✅ Migration complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next: Test each service"
Write-Host "  cd ingestion && pytest tests"
Write-Host "  cd ../vector-store && pytest tests"
Write-Host "  cd ../rag-engine && pytest tests"
Write-Host "  cd ../embedding-server && pytest tests"
