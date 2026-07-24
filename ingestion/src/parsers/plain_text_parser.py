"""Plain text document parser — the fallback parser for .txt sources
and the default for any unrecognized extension."""
from .r2_client import get_object_bytes


class PlainTextParser:
    def extract(self, r2_uri: str) -> str:
        raw_bytes = get_object_bytes(r2_uri)
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # Legacy clinical documents sometimes arrive in Latin-1
            return raw_bytes.decode("latin-1")
