"""
PDF text extraction via PyMuPDF.

Import note: `import pymupdf` is the current recommended import — the
legacy `import fitz` alias still works identically but new code should
prefer `pymupdf` (see docs/PHASE_4_IMPLEMENTATION_PLAN.md footnote [1]).
"""
import pymupdf

from .r2_client import get_object_bytes


class PDFParser:
    """Extract page-by-page text from a PDF stored in R2."""

    def extract(self, r2_uri: str) -> str:
        pdf_bytes = get_object_bytes(r2_uri)
        parts: list[str] = []
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            for i, page in enumerate(doc):
                text = page.get_text("text").strip()
                if text:
                    parts.append(f"[Page {i + 1}]\n{text}")
        return "\n\n".join(parts)
