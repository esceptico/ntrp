import logging
import sys

import structlog

renderer = structlog.dev.ConsoleRenderer(colors=True)

processors = [
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="%H:%M:%S"),
    renderer,
]


def configure_logging(level: str = "INFO"):
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        logger_factory=structlog.WriteLoggerFactory(file=sys.stderr),
    )
    for name in ("googleapiclient.discovery_cache", "LiteLLM", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str | None = None):
    return structlog.get_logger(name or "ntrp")


formatter = {
    "()": structlog.stdlib.ProcessorFormatter,
    "processor": renderer,
    "foreign_pre_chain": processors[:-1],
}

UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"default": formatter, "access": formatter},
    "handlers": {
        "default": {"formatter": "default", "class": "logging.StreamHandler", "stream": "ext://sys.stderr"},
        "access": {"formatter": "access", "class": "logging.StreamHandler", "stream": "ext://sys.stderr"},
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"level": "INFO"},
        "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
}
