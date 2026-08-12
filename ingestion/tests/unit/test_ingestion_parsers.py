"""
Unit tests for ingestion/src/parsers/ — R2 network calls are mocked
throughout (decision: no live R2 credentials needed in CI).
"""
import sys

from unittest.mock import patch
import pytest

class TestR2Client:
    def test_parse_r2_uri_splits_bucket_and_key(self):
        from src.parsers.r2_client import parse_r2_uri
        bucket, key = parse_r2_uri("r2://pvh-documents-dev/raw/tenant/doc/original.pdf")
        assert bucket == "pvh-documents-dev"
        assert key == "raw/tenant/doc/original.pdf"

    def test_rejects_non_r2_uri(self):
        from src.parsers.r2_client import parse_r2_uri
        with pytest.raises(ValueError):
            parse_r2_uri("s3://some-bucket/key")

    def test_rejects_missing_key(self):
        from src.parsers.r2_client import parse_r2_uri
        with pytest.raises(ValueError):
            parse_r2_uri("r2://bucket-only")

    def test_get_r2_client_constructs_without_network_call(self):
        # This IS the CI decision in practice: constructing a boto3 client
        # never touches the network, so no R2 credentials are required to
        # run this test.
        from src.parsers.r2_client import get_r2_client
        client = get_r2_client()
        assert client is not None

class TestPlainTextParser:
    def test_extracts_utf8_text(self):
        from src.parsers.plain_text_parser import PlainTextParser
        with patch("src.parsers.plain_text_parser.get_object_bytes", return_value=b"hello world"):
            result = PlainTextParser().extract("r2://bucket/doc.txt")
        assert result == "hello world"

    def test_falls_back_to_latin1_on_bad_utf8(self):
        from src.parsers.plain_text_parser import PlainTextParser
        latin1_bytes = "café".encode("latin-1")
        with patch("src.parsers.plain_text_parser.get_object_bytes", return_value=latin1_bytes):
            result = PlainTextParser().extract("r2://bucket/legacy.txt")
        assert "caf" in result

class TestPDFParser:
    @staticmethod
    def _make_pdf_bytes(text: str) -> bytes:
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), text)
        data = doc.tobytes()
        doc.close()
        return data

    def test_extracts_text_with_page_marker(self):
        from src.parsers.pdf_parser import PDFParser
        pdf_bytes = self._make_pdf_bytes("Patient HbA1c 8.4 percent")
        with patch("src.parsers.pdf_parser.get_object_bytes", return_value=pdf_bytes):
            result = PDFParser().extract("r2://bucket/note.pdf")
        assert "[Page 1]" in result
        assert "HbA1c" in result

    def test_empty_pdf_returns_empty_string(self):
        from src.parsers.pdf_parser import PDFParser
        pdf_bytes = self._make_pdf_bytes("")
        with patch("src.parsers.pdf_parser.get_object_bytes", return_value=pdf_bytes):
            result = PDFParser().extract("r2://bucket/blank.pdf")
        assert result == ""

class TestHL7Parser:
    _SAMPLE_HL7 = (
        "MSH|^~\\&|SENDER|FAC|RECEIVER|FAC|20260101120000||ORU^R01|MSG001|P|2.3\r"
        "PID|1||123456||Doe^John||19800101|M\r"
        "OBX|1|NM|HBA1C^Hemoglobin A1c||8.4|%|4.0-6.0|H|||F\r"
        "DG1|1|ICD10|E11.9|Type 2 diabetes mellitus\r"
    )

    def test_extracts_observations_and_diagnoses(self):
        from src.parsers.hl7_parser import HL7Parser
        with patch(
            "src.parsers.hl7_parser.get_object_bytes",
            return_value=self._SAMPLE_HL7.encode(),
        ):
            result = HL7Parser().extract("r2://bucket/msg.hl7")
        assert "Obs:" in result
        assert "Dx:" in result

    def test_message_with_no_dg1_segments_does_not_raise(self):
        from src.parsers.hl7_parser import HL7Parser
        no_dg1 = (
            "MSH|^~\\&|SENDER|FAC|RECEIVER|FAC|20260101120000||ORU^R01|MSG002|P|2.3\r"
            "PID|1||654321||Roe^Jane||19750505|F\r"
            "OBX|1|NM|GLU^Glucose||95|mg/dL|70-100|N|||F\r"
        )
        with patch("src.parsers.hl7_parser.get_object_bytes", return_value=no_dg1.encode()):
            result = HL7Parser().extract("r2://bucket/msg2.hl7")
        assert "Obs:" in result
        assert "Dx:" not in result

class TestParserFactory:
    def test_pdf_extension_routes_to_pdf_parser(self):
        from src.parsers import get_parser_for_uri
        from src.parsers.pdf_parser import PDFParser
        assert isinstance(get_parser_for_uri("r2://bucket/doc.pdf"), PDFParser)

    def test_hl7_extension_routes_to_hl7_parser(self):
        from src.parsers import get_parser_for_uri
        from src.parsers.hl7_parser import HL7Parser
        assert isinstance(get_parser_for_uri("r2://bucket/msg.hl7"), HL7Parser)

    def test_txt_extension_routes_to_plain_text_parser(self):
        from src.parsers import get_parser_for_uri
        from src.parsers.plain_text_parser import PlainTextParser
        assert isinstance(get_parser_for_uri("r2://bucket/note.txt"), PlainTextParser)

    def test_unknown_extension_falls_back_to_plain_text(self):
        from src.parsers import get_parser_for_uri
        from src.parsers.plain_text_parser import PlainTextParser
        assert isinstance(get_parser_for_uri("r2://bucket/doc.xyz"), PlainTextParser)
