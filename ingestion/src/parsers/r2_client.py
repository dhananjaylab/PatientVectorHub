"""
R2 (Cloudflare, S3-compatible) client factory for ingestion parsers.

Cloudflare R2 speaks the S3 API, so boto3's generic 's3' client works
unmodified — the only real difference from AWS S3 is endpoint_url, which
must point at R2_ENDPOINT_URL (ADR-009). Every ingestion parser
(pdf_parser.py, hl7_parser.py, plain_text_parser.py) gets its client from
here so there is exactly one place that knows about the R2-vs-AWS
distinction.

CI decision: get_r2_client() only *constructs* a boto3 client object —
that never touches the network on its own, so unit tests can call it with
no live R2 credentials at all. Anything that actually fetches bytes
(get_object_bytes) is mocked out in tests/unit/test_ingestion_parsers.py.
"""
import boto3
from botocore.config import Config

from ..config import settings


def get_r2_client():
    """Return a boto3 S3 client configured for Cloudflare R2.

    R2 requires SigV4 signing and Cloudflare's documented 'path' addressing
    style (not boto3's default 'virtual' bucket addressing), and has no
    regions — 'auto' is the value Cloudflare's own docs specify.
    """
    return boto3.client(
        "s3",
        # boto3/botocore rejects endpoint_url="" outright (raises
        # ValueError: Invalid endpoint) rather than treating it as "unset" —
        # None is the value that actually falls back to default resolution.
        # Matters for local dev / CI where R2_ENDPOINT_URL may be blank.
        endpoint_url=settings.R2_ENDPOINT_URL or None,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="auto",
    )


def parse_r2_uri(uri: str) -> tuple[str, str]:
    """Split an 'r2://bucket/key/path' URI into (bucket, key)."""
    if not uri.startswith("r2://"):
        raise ValueError(f"Expected an r2:// URI, got: {uri!r}")
    bucket_and_key = uri.removeprefix("r2://")
    bucket, _, key = bucket_and_key.partition("/")
    if not key:
        raise ValueError(f"Malformed r2:// URI (no object key): {uri!r}")
    return bucket, key


def get_object_bytes(uri: str) -> bytes:
    """Fetch an object's raw bytes from R2 given an r2:// URI."""
    bucket, key = parse_r2_uri(uri)
    client = get_r2_client()
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()
