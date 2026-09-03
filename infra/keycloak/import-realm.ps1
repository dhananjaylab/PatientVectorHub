# Keycloak realm import script for Windows PowerShell
# This imports the patientvectorhub realm and pvh-spa client into a running Keycloak instance

param(
    [string]$KeycloakUrl = "http://localhost:8080",
    [string]$AdminUsername = "admin",
    [string]$AdminPassword = "admin",
    [string]$RealmFile = "realm.json"
)

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RealmPath = Join-Path $ScriptDir $RealmFile

if (-not (Test-Path $RealmPath)) {
    Write-Error "Realm file not found at: $RealmPath"
    exit 1
}

Write-Host "Keycloak Realm Import Script"
Write-Host "=============================="
Write-Host "Keycloak URL: $KeycloakUrl"
Write-Host "Realm file: $RealmPath"
Write-Host ""

# Step 1: Get admin token
Write-Host "Step 1: Obtaining admin token..."
$tokenUrl = "$KeycloakUrl/realms/master/protocol/openid-connect/token"
$tokenResponse = Invoke-WebRequest -Uri $tokenUrl `
    -Method Post `
    -ContentType "application/x-www-form-urlencoded" `
    -Body @{
        grant_type    = "password"
        client_id     = "admin-cli"
        username      = $AdminUsername
        password      = $AdminPassword
    } -ErrorAction Stop

$token = ($tokenResponse.Content | ConvertFrom-Json).access_token
if (-not $token) {
    Write-Error "Failed to obtain admin token. Check admin credentials."
    exit 1
}
Write-Host "Token obtained"
Write-Host ""

# Step 2: Check if realm already exists
Write-Host "Step 2: Checking if realm exists..."
$realmCheckUrl = "$KeycloakUrl/admin/realms/patientvectorhub"
try {
    $realmResponse = Invoke-WebRequest -Uri $realmCheckUrl `
        -Method Get `
        -Headers @{Authorization = "Bearer $token"} `
        -ErrorAction Stop
    Write-Host "Realm 'patientvectorhub' already exists"
} catch {
    Write-Host "Realm doesn't exist yet (will be created)"
}
Write-Host ""

# Step 3: Import or update the realm
Write-Host "Step 3: Importing realm configuration..."
$realmJson = Get-Content $RealmPath -Raw
$importUrl = "$KeycloakUrl/admin/realms"

try {
    $response = Invoke-WebRequest -Uri $importUrl `
        -Method Post `
        -ContentType "application/json" `
        -Headers @{Authorization = "Bearer $token"} `
        -Body $realmJson `
        -ErrorAction Stop
    Write-Host "Realm imported successfully"
} catch {
    if ($_.Exception.Response.StatusCode -eq 409) {
        Write-Host "Realm already exists with that name"
    } else {
        Write-Error "Failed to import realm: $($_.Exception.Message)"
        exit 1
    }
}
Write-Host ""

# Step 4: Verify clients were created
Write-Host "Step 4: Verifying clients..."
$clientsUrl = "$KeycloakUrl/admin/realms/patientvectorhub/clients"
$clientsResponse = Invoke-WebRequest -Uri $clientsUrl `
    -Method Get `
    -Headers @{Authorization = "Bearer $token"} `
    -ErrorAction Stop

$clients = $clientsResponse.Content | ConvertFrom-Json
$pvhSpaClient = $clients | Where-Object { $_.clientId -eq "pvh-spa" }

if ($pvhSpaClient) {
    Write-Host "Found pvh-spa client"
    Write-Host "  - Client ID: $($pvhSpaClient.id)"
    Write-Host "  - Public client: $($pvhSpaClient.publicClient)"
    Write-Host "  - Standard flow enabled: $($pvhSpaClient.standardFlowEnabled)"
} else {
    Write-Error "pvh-spa client not found after import!"
    exit 1
}
Write-Host ""

# Step 5: Verify users were created
Write-Host "Step 5: Verifying users..."
$usersUrl = "$KeycloakUrl/admin/realms/patientvectorhub/users"
$usersResponse = Invoke-WebRequest -Uri $usersUrl `
    -Method Get `
    -Headers @{Authorization = "Bearer $token"} `
    -ErrorAction Stop

$users = $usersResponse.Content | ConvertFrom-Json
Write-Host "Found $($users.Count) users"
foreach ($user in $users) {
    Write-Host "  - $($user.username)"
}
Write-Host ""

Write-Host "Success! Realm import completed."
Write-Host ""
Write-Host "You can now log in with:"
Write-Host "  URL: http://localhost:5173"
Write-Host "  Username: admin@tenant1.test"
Write-Host "  Password: test-password-123"
