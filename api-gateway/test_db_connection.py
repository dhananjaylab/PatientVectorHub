"""Test database connection to verify connectivity before running migrations."""
import asyncio
import os
import ssl
import sys
from urllib.parse import parse_qs, urlparse

import asyncpg


async def test_connection():
    """Test connection to the database."""
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        print("❌ DATABASE_URL environment variable not set")
        return False

    print(f"Testing connection to: {db_url}")

    try:
        # Parse the asyncpg URL manually since asyncpg.connect doesn't accept sqlalchemy URLs
        # postgresql+asyncpg://user:pass@host:port/dbname?sslmode=require
        parsed = urlparse(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        query_params = parse_qs(parsed.query)

        print(f"  Host: {parsed.hostname}:{parsed.port or 5432}")
        print(f"  Database: {parsed.path.lstrip('/')}")
        print(f"  User: {parsed.username}")
        print(f"  SSL Mode: {query_params.get('sslmode', ['require'])[0]}")

        # Create SSL context for Aiven (no CA verification by default per Aiven docs)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        conn = await asyncpg.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip("/") or "postgres",
            ssl=ssl_context,
            timeout=10,
        )

        version = await conn.fetchval("SELECT version()")
        await conn.close()

        print(f"✅ Connection successful!")
        print(f"   PostgreSQL: {version.split(',')[0]}")
        return True

    except Exception as e:
        print(f"❌ Connection failed: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
