# Start Keycloak with automatic realm import
# This script restarts Keycloak and imports the realm.json from the data/import folder

Write-Host "Starting Keycloak with realm import..." -ForegroundColor Green
Write-Host ""

$keycloakBinPath = "C:\keycloak-26.6.4\bin"
$keycloakCmd = "$keycloakBinPath\kc.bat"

if (-not (Test-Path $keycloakCmd)) {
    Write-Host "ERROR: Keycloak not found at $keycloakCmd" -ForegroundColor Red
    exit 1
}

Write-Host "Keycloak location: $keycloakBinPath" -ForegroundColor Cyan
Write-Host "Realm file location: C:\keycloak-26.6.4\data\import\realm.json" -ForegroundColor Cyan
Write-Host ""

Write-Host "Starting Keycloak in development mode with realm import enabled..." -ForegroundColor Yellow
Write-Host "(You can stop it with Ctrl+C)" -ForegroundColor Gray
Write-Host ""

# Start Keycloak with import-realm flag
# The --import-realm flag tells Keycloak to look in data/import/ for .json files
cd $keycloakBinPath
& $keycloakCmd start-dev --import-realm

# Note: The process will continue running in the foreground
# When you press Ctrl+C, it will stop
