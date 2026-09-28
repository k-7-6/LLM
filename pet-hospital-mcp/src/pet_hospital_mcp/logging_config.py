"""Logging configuration for the Pet Hospital MCP service."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


# Fields that must be redacted in logs
_SENSITIVE_FIELDS = frozenset(
    {
        "owner_phone",
        "ownerphone",
        "owner_addr",
        "owneraddr",
        "chip_no",
        "chipno",
        "ownerName",
        "ownerPhone",
        "ownerAddr",
        "chipNo",
    }
)


def _redact_value(value: Any) -> Any:
    """Redact a sensitive value, keeping only the last 4 characters."""
    if isinstance(value, str) and len(value) > 4:
        return f"***{value[-4:]}"
    return value


def _redact_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact sensitive fields in a dictionary."""
    result = {}
    for key, value in d.items():
        if key.lower() in _SENSITIVE_FIELDS:
            result[key] = _redact_value(value)
        elif isinstance(value, dict):
            result[key] = _redact_dict(value)
        elif isinstance(value, list):
            result[key] = [
                _redact_dict(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


class JsonFormatter(logging.Formatter):
    """JSON log formatter with sensitive field redaction."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with redacted sensitive fields."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Include structured extra fields
        for key in ("tool_name", "params", "status", "duration_ms"):
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
        # Redact sensitive fields from params
        if "params" in log_data and isinstance(log_data["params"], dict):
            log_data["params"] = _redact_dict(log_data["params"])
        # Include exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, default=str, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with JSON formatting."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Remove duplicate handlers
    root.handlers.clear()
    root.addHandler(handler)
    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access", "mcp.server"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
