"""
Structured JSON logging setup for PatientVectorHub.
Produces Loki-compatible JSON lines on stdout.
Call configure_logging() before creating the FastAPI app.
"""
import logging
import sys
import json
import time
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record — Loki/Grafana-compatible."""

    LEVEL_MAP = {
        logging.DEBUG:    "DEBUG",
        logging.INFO:     "INFO",
        logging.WARNING:  "WARN",
        logging.ERROR:    "ERROR",
        logging.CRITICAL: "CRITICAL",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time":    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level":   self.LEVEL_MAP.get(record.levelno, "INFO"),
            "logger":  record.name,
            "msg":     record.getMessage(),
            "service": "pvh-api-gateway",
        }

        # Attach exception info if present
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # Attach extra fields set via logger.info("...", extra={"key": "val"})
        for key, val in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
            ):
                payload[key] = val

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger with JSON output to stdout."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove any existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    # Quieten noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
