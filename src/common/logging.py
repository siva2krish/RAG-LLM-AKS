"""
Structured Logging with Context
================================
Production-grade logging with correlation IDs for distributed tracing.
"""

import structlog
from typing import Any
import logging
import sys
from .config import get_settings


def setup_logging() -> None:
    """Configure structured logging for the application."""
    settings = get_settings()
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            # Use JSON in production, console-friendly in dev
            structlog.processors.JSONRenderer() 
            if settings.is_production 
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Also configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """Get a logger instance with the given name."""
    return structlog.get_logger(name)
