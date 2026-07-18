"""Test database connection to verify connectivity before running migrations."""
import asyncio
import os
import ssl
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import asyncpg
from dotenv import load_dotenv


def mask_url(db_url: str) -> str:
    """Hide passwords before printing database URLs."""
    parsed = urlparse(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    if not parsed.password:
        return db_url
    return db_url.replace(f":{parsed.password}@", ":***@")


async def test_connection():
    """Test connection to the configured cloud database."""
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        print("DATABASE_URL environment variable not set")
        return False

    print(f"Testing connection to: {mask_url(db_url)}")

    try:
        # asyncpg.connect does not accept SQLAlchemy driver names in URLs.
        parsed = urlparse(db_url.replace("postgresql+asyncpg://", "postgresql://"))
        query_params = parse_qs(parsed.query)

        print(f"  Host: {parsed.hostname}:{parsed.port or 5432}")
        print(f"  Database: {parsed.path.lstrip('/')}")
        print(f"  User: {parsed.username}")
        print(f"  SSL Mode: {query_params.get('sslmode', ['require'])[0]}")

        ssl_context = None
        if query_params.get("sslmode", [""])[0] in {"require", "verify-ca", "verify-full"}:
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

        print("Connection successful")
        print(f"   PostgreSQL: {version.split(',')[0]}")
        return True

    except Exception as e:
        print(f"Connection failed: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)