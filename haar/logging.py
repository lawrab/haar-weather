"""Logging configuration for Haar weather prediction system."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

from haar.config import HaarConfig, LoggingConfig


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color-coded log levels."""

    COLORS = {
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold red",
    }

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        """Initialize formatter.

        Args:
            fmt: Log message format string
            datefmt: Date format string
        """
        super().__init__(fmt, datefmt)
        self.console = Console(file=sys.stderr)

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors.

        Args:
            record: Log record to format

        Returns:
            Formatted log message
        """
        return super().format(record)


def setup_logging(
    config: Optional[LoggingConfig] = None,
    verbose: int = 0,
    log_file: Optional[Path] = None,
) -> None:
    """Configure logging for the application.

    Args:
        config: Logging configuration (uses default if None)
        verbose: Verbosity level (0=config level, 1=INFO, 2=DEBUG, 3+=DEBUG with details)
        log_file: Override log file path
    """
    # Get default config if not provided
    if config is None:
        from haar.config import get_config

        haar_config = get_config()
        config = haar_config.logging

    # Determine log level based on verbosity
    if verbose == 0:
        level = getattr(logging, config.level)
    elif verbose == 1:
        level = logging.INFO
    else:  # verbose >= 2
        level = logging.DEBUG

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create formatters
    file_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_formatter = logging.Formatter(
        fmt="%(message)s",
        datefmt="%H:%M:%S",
    )

    # Add file handler if configured
    if log_file or config.file:
        file_path = log_file or config.file

        # Ensure log directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            filename=file_path,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Add console handler if configured
    if config.console:
        # Use Rich handler for better formatting
        console_handler = RichHandler(
            console=Console(stderr=True),
            show_time=True,
            show_path=verbose >= 3,  # Show file paths only in very verbose mode
            markup=True,
            rich_tracebacks=True,
            tracebacks_show_locals=verbose >= 3,
        )
        console_handler.setLevel(level)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Set third-party library log levels to reduce noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # Log initial message at debug level
    logger = logging.getLogger(__name__)
    logger.debug(
        f"Logging configured: level={logging.getLevelName(level)}, "
        f"file={'enabled' if (log_file or config.file) else 'disabled'}, "
        f"console={'enabled' if config.console else 'disabled'}"
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
