# Keycloak Realm Import

## Problem
When you enable `VITE_AUTH_ENABLED=true` in the dashboard, the app tries to authenticate via Keycloak but fails because:
1. The `pvh-spa` client isn't configured in the realm
2. The test users don't exist in Keycloak
3. The OAuth flow can't complete

## Solution: Use Keycloak's Import Feature

Keycloak supports importing a realm at startup using the `KEYCLOAK_IMPORT` environment variable.

### Steps:

1. **Stop Keycloak** (if running)
   ```cmd
   Ctrl+C
   ```

2. **Restart Keycloak with import enabled:**
   ```cmd
   cd C:\keycloak-26.6.4\bin
   kc.bat start-dev --import-realm
   ```

3. **Keycloak will automatically:**
   - Look for `.json` files in `data/import/` folder
   - Import the realm from those files
   - Create all clients, users, and roles defined in the JSON

### Setup the Import Folder:

Since we're running Keycloak in dev mode from `C:\keycloak-26.6.4\`, we need to put the realm.json in the right place.

Option 1: Copy realm.json to Keycloak's import folder:
```cmd
mkdir C:\keycloak-26.6.4\data\import
copy C:\PatientVectorHub\infra\keycloak\realm.json C:\keycloak-26.6.4\data\import\
```

Option 2: Use a symlink (Windows):
```cmd
mklink /D C:\keycloak-26.6.4\data\import C:\PatientVectorHub\infra\keycloak
```

4. **Verify the realm was imported:**
   - Open http://localhost:8080/admin
   - Log in with admin:admin
   - Select the "patientvectorhub" realm in the dropdown (top-left)
   - Check that clients (pvh-spa, pvh-backend) exist
   - Check that users exist

5. **Now you can enable auth:**
   - Set `VITE_AUTH_ENABLED=true` in `dashboard/.env.local`
   - Set `AUTH_ENABLED=true` in `.env` (root)
   - Restart both services

## Troubleshooting

If the realm still won't import:

1. **Check Keycloak logs** for errors about the import file
2. **Ensure realm.json is valid JSON** (no syntax errors)
3. **Try manual import:**
   ```bash
   # Get admin token
   curl -X POST http://localhost:8080/realms/master/protocol/openid-connect/token \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "grant_type=password&client_id=admin-cli&username=admin&password=admin"
   
   # Import realm (replace TOKEN with the access_token from above)
   curl -X POST http://localhost:8080/admin/realms \
     -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     -d @realm.json
   ```

## Alternative: Stay Disabled for Now

If Keycloak keeps causing issues, you can keep auth disabled locally:

```env
# .env (root)
AUTH_ENABLED=false

# dashboard/.env.local
VITE_AUTH_ENABLED=false
```

This lets you develop and test the app without the auth layer, then enable it once Keycloak is properly configured.
