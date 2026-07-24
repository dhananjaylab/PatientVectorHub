"""Parser factory — dispatches on file extension.

source_path in the documents table (migration 004) is a free-text URI —
for R2 it's shaped like
  r2://{bucket}/raw/{tenant_id}/{patient_id}/{doc_id}/original.{ext}
matching what scripts/seed_data.py's sample documents already write.
"""
from .hl7_parser import HL7Parser
from .pdf_parser import PDFParser
from .plain_text_parser import PlainTextParser

_PARSERS = {
    "pdf": PDFParser,
    "hl7": HL7Parser,
    "txt": PlainTextParser,
    "text": PlainTextParser,
}


def get_parser_for_uri(r2_uri: str):
    """Return a parser instance appropriate for the document's extension.
    Unrecognized extensions fall back to plain-text parsing rather than
    raising — matches the original doc 21 reference behavior."""
    ext = r2_uri.lower().rsplit(".", 1)[-1] if "." in r2_uri else ""
    parser_cls = _PARSERS.get(ext, PlainTextParser)
    return parser_cls()
