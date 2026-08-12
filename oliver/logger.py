# Path: logger.py
# Description: JSON structured logger with request context correlation for Azure logs.

import json
import logging
import logging.config
from functools import lru_cache

from config import get_settings

# Get the settings
settings = get_settings()


class RequestContextFilter(logging.Filter):
    """
    Logging filter that adds request context (request_id, endpoint, method)
    to every log record.
    """

    def filter(self, record):
        # Import here to avoid circular imports
        import re

        from utils import request_context

        # Get current request context
        context = request_context.get_request_context()

        # Add context fields to log record
        record.request_id = context.get("request_id", "-")
        record.endpoint = context.get("endpoint", "-")
        record.method = context.get("method", "-")

        # Special handling for uvicorn.access logs
        # These logs don't go through middleware, so we parse the message
        if record.name == "uvicorn.access":
            message = record.getMessage()
            # Parse format: 'IP:PORT - "METHOD /endpoint HTTP/1.1" STATUS_CODE'
            match = re.search(r'"(\w+)\s+([^\s]+)\s+HTTP', message)
            if match:
                record.method = match.group(1)
                record.endpoint = match.group(2)

            status_match = re.search(r'"\s+(\d{3})', message)
            if status_match:
                record.status_code = status_match.group(1)

        return True


class JsonFormatter(logging.Formatter):
    """
    JSON formatter for structured logging compatible with Azure logs.
    """

    def format(self, record):
        log_data = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add request context fields (always present due to RequestContextFilter)
        log_data["request_id"] = record.request_id
        log_data["endpoint"] = record.endpoint
        log_data["method"] = record.method

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


@lru_cache
def get_logger():
    """Get a logger instance."""
    logger = logging.getLogger(__name__)
    logger.setLevel(settings.LOGGING_LEVEL.upper())

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_context": {
                "()": RequestContextFilter,
            }
        },
        "formatters": {
            "json": {
                "()": JsonFormatter,
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "handlers": {
            "json_stdout": {
                "formatter": "json",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": ["request_context"],
            },
        },
        "loggers": {
            "": {"handlers": ["json_stdout"], "level": settings.LOGGING_LEVEL.upper()},
            "uvicorn.error": {
                "handlers": ["json_stdout"],
                "level": settings.LOGGING_LEVEL.upper(),
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["json_stdout"],
                "level": settings.LOGGING_LEVEL.upper(),
                "propagate": False,
            },
            # Suppress noisy libraries
            "httpx": {
                "handlers": ["json_stdout"],
                "level": settings.LOGGING_LEVEL.upper(),
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["json_stdout"],
                "level": settings.LOGGING_LEVEL.upper(),
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "handlers": ["json_stdout"],
                "level": settings.LOGGING_LEVEL.upper(),
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(logging_config)

    return logger
