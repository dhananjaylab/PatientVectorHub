# Move api-gateway tests from root tests/ to api-gateway/tests/

$repoRoot = "a:\PatientVectorHub"
$sourceUnitDir = "$repoRoot\tests\unit"
$sourceIntegrationDir = "$repoRoot\tests\integration"

$destUnitDir = "$repoRoot\api-gateway\tests\unit"
$destIntegrationDir = "$repoRoot\api-gateway\tests\integration"

# API Gateway unit tests
$unitTests = @(
    "test_auth_middleware.py",
    "test_errors.py",
    "test_phase1_health.py",
    "test_query_router.py",
    "test_rbac.py",
    "test_seed_data.py"
)

# API Gateway integration tests
$integrationTests = @(
    "test_rls_isolation.py",
    "test_rls_isolation_core_tables.py",
    "test_stack_connectivity.py"
)

Write-Host "Moving API Gateway unit tests..." -ForegroundColor Green
foreach ($test in $unitTests) {
    $src = "$sourceUnitDir\$test"
    $dst = "$destUnitDir\$test"
    
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "  ✓ Copied $test"
    }
    else {
        Write-Host "  ⚠ Not found: $test"
    }
}

Write-Host "`nMoving API Gateway integration tests..." -ForegroundColor Green
foreach ($test in $integrationTests) {
    $src = "$sourceIntegrationDir\$test"
    $dst = "$destIntegrationDir\$test"
    
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "  ✓ Copied $test"
    }
    else {
        Write-Host "  ⚠ Not found: $test"
    }
}

Write-Host "`n✅ Copy complete" -ForegroundColor Green
Write-Host "Now updating imports..." -ForegroundColor Cyan

# Function to update sys.path in test files
function Update-TestFileImports {
    param (
        [string]$filePath
    )
    
    $content = Get-Content $filePath -Raw
    
    # Remove sys.path.insert lines
    $content = $content -replace "import sys\s*\n\s*import os\s*\n\s*sys\.path\.insert\(0,.*?\)\s*\n+", ""
    
    # Clean up extra blank lines
    $content = $content -replace "\n{3,}", "`n`n"
    
    Set-Content $filePath $content -Encoding UTF8
}

Write-Host "Updating unit tests..." -ForegroundColor Green
foreach ($test in $unitTests) {
    $dst = "$destUnitDir\$test"
    if (Test-Path $dst) {
        Update-TestFileImports $dst
        Write-Host "  ✓ Updated imports in $test"
    }
}

Write-Host "Updating integration tests..." -ForegroundColor Green
foreach ($test in $integrationTests) {
    $dst = "$destIntegrationDir\$test"
    if (Test-Path $dst) {
        Update-TestFileImports $dst
        Write-Host "  ✓ Updated imports in $test"
    }
}

Write-Host "`n✅ All done!" -ForegroundColor Green
Write-Host "`nNext: cd api-gateway && pytest tests" -ForegroundColor Cyan
