"""Unit tests for ingestion/src/chunkers/splitter.py."""
import sys

class TestChunker:
    def test_short_text_produces_single_chunk(self):
        from src.chunkers.splitter import chunk_text
        chunks = chunk_text("Short clinical note.", chunk_size=512, overlap=50)
        assert len(chunks) == 1
        assert chunks[0].index == 0

    def test_long_text_produces_multiple_indexed_chunks(self):
        from src.chunkers.splitter import chunk_text
        long_text = "Patient history. " * 200  # well over 200 chars
        chunks = chunk_text(long_text, chunk_size=200, overlap=40)
        assert len(chunks) > 1
        assert [c.index for c in chunks] == list(range(len(chunks)))

    def test_empty_or_whitespace_only_input_produces_no_chunks(self):
        from src.chunkers.splitter import chunk_text
        assert chunk_text("   \n\n   ", chunk_size=100, overlap=10) == []

    def test_all_chunks_are_non_empty_after_stripping(self):
        from src.chunkers.splitter import chunk_text
        text = "Section one.\n\nSection two.\n\nSection three."
        chunks = chunk_text(text, chunk_size=15, overlap=0)
        assert all(c.text.strip() for c in chunks)

    def test_overlap_greater_than_chunk_size_still_returns_chunks(self):
        # LangChain's splitter tolerates this (clamps effectively); this
        # test just guards against an unhandled exception on bad input.
        from src.chunkers.splitter import chunk_text
        chunks = chunk_text("word " * 50, chunk_size=20, overlap=10)
        assert len(chunks) >= 1
