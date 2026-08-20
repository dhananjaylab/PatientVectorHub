$ErrorActionPreference = 'Stop'

Set-Location $PSScriptRoot

$listener = Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
  $listener.OwningProcess | Sort-Object -Unique | ForEach-Object {
    Stop-Process -Id $_ -Force
  }
}

$env:VITE_AUTH_ENABLED = 'true'
$env:VITE_KEYCLOAK_URL = 'http://localhost:8080'
$env:VITE_KEYCLOAK_REALM = 'patientvectorhub'
$env:VITE_KEYCLOAK_CLIENT_ID = 'pvh-spa'

npm run dev