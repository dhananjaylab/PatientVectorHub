# PowerShell script to run tests with common options
# Usage: .\run_tests.ps1 [unit|integration|all] [options]

param(
    [Parameter(Position = 0)]
    [ValidateSet('unit', 'integration', 'all', 'help')]
    [string]$TestType = 'all',
    
    [switch]$Coverage,
    [switch]$Verbose,
    [switch]$Watch
)

function Show-Help {
    @"
Usage: .\run_tests.ps1 [unit|integration|all] [options]

Commands:
  unit           Run only unit tests (no Docker required)
  integration    Run only integration tests (requires Docker)
  all            Run all tests (default)
  help           Show this help message

Options:
  -Coverage      Generate coverage report
  -Verbose       Show verbose output
  -Watch         Watch for changes and rerun (requires pytest-watch)

Examples:
  .\run_tests.ps1 unit
  .\run_tests.ps1 integration -Verbose
  .\run_tests.ps1 all -Coverage
  .\run_tests.ps1 unit -Watch
"@
}

if ($TestType -eq 'help') {
    Show-Help
    exit 0
}

# Build pytest command
$cmd = 'pytest'
$args = @('-v', '--tb=short')

if ($TestType -eq 'unit') {
    $args += '-m', 'unit'
    Write-Host "Running unit tests (no Docker required)..." -ForegroundColor Green
}
elseif ($TestType -eq 'integration') {
    $args += '-m', 'integration'
    Write-Host "Running integration tests (requires Docker)..." -ForegroundColor Yellow
}
else {
    Write-Host "Running all tests..." -ForegroundColor Green
}

if ($Coverage) {
    $args += '--cov=src', '--cov-report=html', '--cov-report=term'
}

if ($Verbose) {
    # Already have -v, add more details
    $args += '--capture=no'
}

# Execute pytest
if ($Watch) {
    # Try to use pytest-watch if available
    $cmd = 'ptw'
    Write-Host "Watching for changes (press Ctrl+C to stop)..." -ForegroundColor Cyan
}

Write-Host "`nExecuting: $cmd $($args -join ' ')`n" -ForegroundColor Cyan
& $cmd @args
