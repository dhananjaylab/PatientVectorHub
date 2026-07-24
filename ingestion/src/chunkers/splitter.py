"""
Text chunking for the ingestion pipeline.

Import note: RecursiveCharacterTextSplitter now lives in the standalone
langchain-text-splitters package (`from langchain_text_splitters import
RecursiveCharacterTextSplitter`), not the monolithic langchain package's
`langchain.text_splitter` module the reference docs (07-12, 19-24) were
written against — see docs/PHASE_4_IMPLEMENTATION_PLAN.md footnote [3].

RawChunk is deliberately independent of vector_store.interface.Chunk —
the chunker has no dependency on the vector-store package at all. The
translation from RawChunk to vector_store's Chunk contract happens in
ingestion/src/workers/batch_worker.py, the one place that actually needs
both packages (parsing/chunking/embedding on one side, vector storage on
the other). See MANUAL_INTEGRATION_NOTES.md for the cross-service import
wiring this implies.
"""
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

# Ordered from strongest to weakest boundary — keeps clinical documents'
# natural structure (sections, sentences) intact as long as possible
# before falling back to word/character splits.
_CLINICAL_SEPARATORS = ["\n\n", "\n", ". ", ", ", " ", ""]


@dataclass
class RawChunk:
    text: str
    index: int


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[RawChunk]:
    """Split raw document text into overlapping chunks.

    Args:
        text: Raw extracted document text (from any parser in
              ingestion/src/parsers/).
        chunk_size: Target chunk size in characters.
        overlap: Character overlap between adjacent chunks.

    Returns:
        Ordered list of RawChunk; empty/whitespace-only pieces are dropped.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=_CLINICAL_SEPARATORS,
        length_function=len,
        is_separator_regex=False,
    )
    pieces = splitter.split_text(text)
    return [RawChunk(text=p, index=i) for i, p in enumerate(pieces) if p.strip()]
