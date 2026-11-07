"""
app/core/logging_config.py
Zero-budget, high-reliability logging configuration supporting standard text
and structured JSON formats with request ID correlation and sensitive data redaction.
"""
import re
import json
import logging
import contextvars
from datetime import datetime, timezone
from typing import Optional, Any, Dict

request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)

# Keys containing sensitive secrets or tenant document text that must NEVER appear in logs
SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "secret_key",
    "authorization",
    "cookie",
    "credentials",
    "api_key",
    # Sensitive document contents / tenant text
    "extracted_text",
    "document_text",
    "raw_text",
    "structured_content",
    "file_bytes",
    "raw_bytes",
    "text_content",
}

# Regex to scrub sensitive values in exception strings
EXCEPTION_REDACT_REGEX = re.compile(
    r"(?i)(password|token|secret|key|authorization|bearer)\s*[=:]\s*['\"]?[^\s,;'\"]+",
    re.IGNORECASE
)


def _redact_sensitive(data: Any) -> Any:
    """Recursively redacts sensitive dictionary keys."""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = _redact_sensitive(v)
        return cleaned
    elif isinstance(data, list):
        return [_redact_sensitive(item) for item in data]
    return data


class JSONLogFormatter(logging.Formatter):
    """
    Structured JSON formatter for production log aggregation (Docker, Loki, Datadog).
    Includes ISO-8601 UTC timestamp, log level, logger name, message, and request_id.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include correlated request_id if available
        req_id = getattr(record, "request_id", None) or request_id_ctx.get()
        if req_id:
            log_payload["request_id"] = req_id

        # Include optional event classification
        if hasattr(record, "event") and record.event:
            log_payload["event"] = record.event

        # Include extra payload if attached
        if hasattr(record, "payload") and isinstance(record.payload, dict):
            log_payload["data"] = _redact_sensitive(record.payload)

        # Include exception info safely without sensitive traces
        if record.exc_info:
            raw_exc = self.formatException(record.exc_info)
            log_payload["exception"] = EXCEPTION_REDACT_REGEX.sub(r"\1=[REDACTED]", raw_exc)

        return json.dumps(log_payload, default=str)


class TextLogFormatter(logging.Formatter):
    """
    Standard human-readable log formatter for development and testing.
    """

    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", None) or request_id_ctx.get()
        prefix = f" [req_id={req_id}]" if req_id else ""
        original_msg = record.msg
        record.msg = f"{prefix} {original_msg}" if prefix else original_msg
        try:
            return super().format(record)
        finally:
            record.msg = original_msg


def setup_logging(log_format: str = "text", level: int = logging.INFO) -> None:
    """
    Configures the root and application loggers with the selected format.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing stream handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()
    if log_format.lower() == "json":
        handler.setFormatter(JSONLogFormatter())
    else:
        handler.setFormatter(
            TextLogFormatter("%(asctime)s [%(levelname)s] [%(name)s]%(message)s")
        )

    root_logger.addHandler(handler)

    # Ensure brandguard logger propagates to root
    brandguard_logger = logging.getLogger("brandguard")
    brandguard_logger.setLevel(level)
