#!/usr/bin/env python3
"""
Keycloak realm import script.
Imports the patientvectorhub realm, clients, and users from realm.json.
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
except ImportError:
    print("Error: requests library not installed. Install with: pip install requests")
    sys.exit(1)


class KeycloakImporter:
    def __init__(
        self,
        keycloak_url: str = "http://localhost:8080",
        admin_user: str = "admin",
        admin_pass: str = "admin",
        realm_file: str = "realm.json",
    ):
        self.keycloak_url = keycloak_url.rstrip("/")
        self.admin_user = admin_user
        self.admin_pass = admin_pass
        self.realm_file = Path(realm_file)
        self.token = None
        self.session = requests.Session()
        self.session.verify = False  # For local dev only
        
    def log(self, message: str, prefix: str = ""):
        print(f"{prefix}{message}")
    
    def get_token(self) -> bool:
        """Obtain admin access token"""
        self.log("Obtaining admin token...")
        
        token_url = urljoin(
            self.keycloak_url,
            "/realms/master/protocol/openid-connect/token"
        )
        
        try:
            resp = self.session.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": self.admin_user,
                    "password": self.admin_pass,
                },
                timeout=10,
            )
            resp.raise_for_status()
            self.token = resp.json().get("access_token")
            if not self.token:
                self.log("Error: No access_token in response", "✗ ")
                return False
            self.log("Token obtained", "✓ ")
            return True
        except Exception as e:
            self.log(f"Error: {e}", "✗ ")
            return False
    
    def get_headers(self) -> dict:
        """Get request headers with authorization"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
    
    def import_realm(self) -> bool:
        """Import realm from JSON file"""
        if not self.realm_file.exists():
            self.log(f"Error: {self.realm_file} not found", "✗ ")
            return False
        
        self.log("Importing realm...")
        
        with open(self.realm_file) as f:
            realm_json = json.load(f)
        
        realm_url = urljoin(self.keycloak_url, "/admin/realms")
        
        try:
            resp = self.session.post(
                realm_url,
                json=realm_json,
                headers=self.get_headers(),
                timeout=10,
            )
            if resp.status_code in (201, 204):
                self.log("Realm imported", "✓ ")
                return True
            elif resp.status_code == 409:
                self.log("Realm already exists", "ℹ ")
                return True
            else:
                self.log(f"Error: HTTP {resp.status_code}", "✗ ")
                self.log(f"Response: {resp.text}")
                return False
        except Exception as e:
            self.log(f"Error: {e}", "✗ ")
            return False
    
    def verify_realm(self) -> bool:
        """Verify realm was created"""
        self.log("Verifying realm...")
        
        realm_url = urljoin(
            self.keycloak_url,
            "/admin/realms/patientvectorhub"
        )
        
        try:
            resp = self.session.get(
                realm_url,
                headers=self.get_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            self.log("Realm verified", "✓ ")
            return True
        except Exception as e:
            self.log(f"Error: {e}", "✗ ")
            return False
    
    def verify_clients(self) -> bool:
        """Verify pvh-spa client exists"""
        self.log("Verifying pvh-spa client...")
        
        clients_url = urljoin(
            self.keycloak_url,
            "/admin/realms/patientvectorhub/clients"
        )
        
        try:
            resp = self.session.get(
                clients_url,
                headers=self.get_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            clients = resp.json()
            
            pvh_spa = next(
                (c for c in clients if c.get("clientId") == "pvh-spa"),
                None
            )
            
            if pvh_spa:
                self.log(f"Found pvh-spa client (ID: {pvh_spa['id']})", "✓ ")
                self.log(f"  - Public: {pvh_spa.get('publicClient')}")
                self.log(f"  - Standard flow: {pvh_spa.get('standardFlowEnabled')}")
                return True
            else:
                self.log("Error: pvh-spa client not found", "✗ ")
                return False
        except Exception as e:
            self.log(f"Error: {e}", "✗ ")
            return False
    
    def verify_users(self) -> bool:
        """Verify test users exist"""
        self.log("Verifying test users...")
        
        users_url = urljoin(
            self.keycloak_url,
            "/admin/realms/patientvectorhub/users"
        )
        
        try:
            resp = self.session.get(
                users_url,
                headers=self.get_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            users = resp.json()
            
            if users:
                self.log(f"Found {len(users)} users", "✓ ")
                for user in users:
                    self.log(f"  - {user['username']}")
                return True
            else:
                self.log("Error: No users found", "✗ ")
                return False
        except Exception as e:
            self.log(f"Error: {e}", "✗ ")
            return False
    
    def run(self) -> bool:
        """Run the full import process"""
        print("=" * 50)
        print("Keycloak Realm Import Script")
        print("=" * 50)
        print(f"Keycloak URL: {self.keycloak_url}")
        print(f"Realm file: {self.realm_file}")
        print()
        
        if not self.get_token():
            return False
        print()
        
        if not self.import_realm():
            return False
        print()
        
        # Small delay to allow realm to be created
        time.sleep(1)
        
        if not self.verify_realm():
            return False
        print()
        
        if not self.verify_clients():
            return False
        print()
        
        if not self.verify_users():
            return False
        print()
        
        print("✅ Realm import completed successfully!")
        print()
        print("You can now log in with:")
        print("  URL: http://localhost:5173")
        print("  Username: admin@tenant1.test")
        print("  Password: test-password-123")
        print()
        
        return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Import Keycloak realm and users"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="Keycloak URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--user",
        default="admin",
        help="Admin username (default: admin)",
    )
    parser.add_argument(
        "--pass",
        dest="password",
        default="admin",
        help="Admin password (default: admin)",
    )
    parser.add_argument(
        "--file",
        default="realm.json",
        help="Realm JSON file (default: realm.json)",
    )
    
    args = parser.parse_args()
    
    importer = KeycloakImporter(
        keycloak_url=args.url,
        admin_user=args.user,
        admin_pass=args.password,
        realm_file=args.file,
    )
    
    success = importer.run()
    sys.exit(0 if success else 1)
