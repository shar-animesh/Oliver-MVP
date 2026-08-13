# Path: app/logger.py
# Description: JSON structured logging with request correlation.

import json
import logging
import logging.config
import re
from functools import lru_cache

from app.config import get_settings
from app.utils import request_context

settings = get_settings()


class RequestContextFilter(logging.Filter):
    """Attach request correlation fields to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = request_context.get_request_context()
        record.request_id = context.get("request_id", "-")
        record.endpoint = context.get("endpoint", "-")
        record.method = context.get("method", "-")

        if record.name == "uvicorn.access":
            message = record.getMessage()
            if match := re.search(r'"(\w+)\s+([^\s]+)\s+HTTP', message):
                record.method = match.group(1)
                record.endpoint = match.group(2)
        return True


class JsonFormatter(logging.Formatter):
    """Serialize application and server logs for structured ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "request_id": getattr(record, "request_id", "-"),
            "endpoint": getattr(record, "endpoint", "-"),
            "method": getattr(record, "method", "-"),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


@lru_cache
def get_logger() -> logging.Logger:
    """Configure process logging once and return the application logger."""
    level = settings.LOG_LEVEL.upper()
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"request_context": {"()": RequestContextFilter}},
        "formatters": {"json": {"()": JsonFormatter}},
        "handlers": {
            "json_stdout": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "filters": ["request_context"],
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "": {"handlers": ["json_stdout"], "level": level},
            "uvicorn.error": {"handlers": ["json_stdout"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["json_stdout"], "level": level, "propagate": False},
            "httpx": {"handlers": ["json_stdout"], "level": "WARNING", "propagate": False},
            "httpcore": {"handlers": ["json_stdout"], "level": "WARNING", "propagate": False},
        },
    }
    logging.config.dictConfig(logging_config)
    return logging.getLogger("oliver-admin-dashboard")
