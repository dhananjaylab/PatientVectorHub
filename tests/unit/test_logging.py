"""Unit tests for structured JSON logging configuration."""
import sys, os, json, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api-gateway"))

from io import StringIO
from src.logging_config import JsonFormatter, configure_logging


class TestJsonFormatter:
    def _get_record(self, msg: str, level=logging.INFO) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test.logger", level=level,
            pathname="", lineno=0, msg=msg,
            args=(), exc_info=None,
        )
        return record

    def test_output_is_valid_json(self):
        fmt = JsonFormatter()
        output = fmt.format(self._get_record("hello world"))
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_output_has_required_fields(self):
        fmt = JsonFormatter()
        parsed = json.loads(fmt.format(self._get_record("test")))
        assert "time"    in parsed
        assert "level"   in parsed
        assert "logger"  in parsed
        assert "msg"     in parsed
        assert "service" in parsed

    def test_message_preserved(self):
        fmt = JsonFormatter()
        parsed = json.loads(fmt.format(self._get_record("specific message")))
        assert parsed["msg"] == "specific message"

    def test_service_name_correct(self):
        fmt = JsonFormatter()
        parsed = json.loads(fmt.format(self._get_record("x")))
        assert parsed["service"] == "pvh-api-gateway"

    def test_info_level_mapped(self):
        fmt = JsonFormatter()
        parsed = json.loads(fmt.format(self._get_record("x", logging.INFO)))
        assert parsed["level"] == "INFO"

    def test_error_level_mapped(self):
        fmt = JsonFormatter()
        parsed = json.loads(fmt.format(self._get_record("x", logging.ERROR)))
        assert parsed["level"] == "ERROR"

    def test_warning_mapped_to_warn(self):
        fmt = JsonFormatter()
        parsed = json.loads(fmt.format(self._get_record("x", logging.WARNING)))
        assert parsed["level"] == "WARN"

    def test_time_is_iso_format(self):
        fmt = JsonFormatter()
        parsed = json.loads(fmt.format(self._get_record("x")))
        assert "T" in parsed["time"]
        assert "Z" in parsed["time"]


class TestConfigureLogging:
    def test_configure_logging_does_not_raise(self):
        configure_logging("INFO")   # should complete silently

    def test_configure_logging_sets_level(self):
        configure_logging("DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        configure_logging("INFO")   # reset

    def test_root_logger_has_handler_after_configure(self):
        configure_logging("INFO")
        root = logging.getLogger()
        assert len(root.handlers) >= 1
