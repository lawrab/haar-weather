"""Tests for logging configuration."""

import logging
from pathlib import Path

import pytest

from haar.config import LoggingConfig
from haar.logging import get_logger, setup_logging


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration before each test."""
    # Clear all handlers before test
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)
    yield
    # Clear all handlers after test
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)


def test_setup_logging_default():
    """Test logging setup with default configuration."""
    config = LoggingConfig()
    setup_logging(config)

    root_logger = logging.getLogger()
    assert root_logger.level == logging.INFO
    assert len(root_logger.handlers) > 0


def test_setup_logging_debug_level():
    """Test logging setup with DEBUG level."""
    config = LoggingConfig(level="DEBUG")
    setup_logging(config)

    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG


def test_setup_logging_file_handler(tmp_path):
    """Test file handler creation."""
    log_file = tmp_path / "test.log"
    config = LoggingConfig(file=log_file, console=False)

    setup_logging(config)

    # Log a message
    logger = logging.getLogger("test")
    logger.info("Test message")

    # Check file was created and contains message
    assert log_file.exists()
    log_content = log_file.read_text()
    assert "Test message" in log_content
    assert "test" in log_content  # Logger name


def test_setup_logging_creates_log_directory(tmp_path):
    """Test that log directory is created if it doesn't exist."""
    log_file = tmp_path / "logs" / "nested" / "test.log"
    config = LoggingConfig(file=log_file, console=False)

    setup_logging(config)

    assert log_file.parent.exists()
    assert log_file.parent.is_dir()


def test_setup_logging_console_handler():
    """Test console handler creation."""
    config = LoggingConfig(console=True)
    setup_logging(config)

    root_logger = logging.getLogger()
    # Should have at least console handler
    assert any(
        handler.__class__.__name__ == "RichHandler" for handler in root_logger.handlers
    )


def test_setup_logging_no_console():
    """Test logging without console handler."""
    config = LoggingConfig(console=False)
    setup_logging(config)

    root_logger = logging.getLogger()
    # Should not have RichHandler
    assert not any(
        handler.__class__.__name__ == "RichHandler" for handler in root_logger.handlers
    )


def test_setup_logging_verbosity_levels(tmp_path):
    """Test verbosity levels override config level."""
    log_file = tmp_path / "test.log"
    config = LoggingConfig(level="WARNING", file=log_file, console=False)

    # verbose=0: use config level (WARNING)
    setup_logging(config, verbose=0)
    assert logging.getLogger().level == logging.WARNING

    # verbose=1: INFO
    setup_logging(config, verbose=1)
    assert logging.getLogger().level == logging.INFO

    # verbose=2: DEBUG
    setup_logging(config, verbose=2)
    assert logging.getLogger().level == logging.DEBUG

    # verbose=3: DEBUG (same as 2)
    setup_logging(config, verbose=3)
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_rotating_file_handler(tmp_path):
    """Test rotating file handler configuration."""
    log_file = tmp_path / "test.log"
    config = LoggingConfig(
        file=log_file, console=False, max_bytes=1024, backup_count=3
    )

    setup_logging(config)

    # Check that a RotatingFileHandler was created
    root_logger = logging.getLogger()
    rotating_handlers = [
        h for h in root_logger.handlers if h.__class__.__name__ == "RotatingFileHandler"
    ]

    assert len(rotating_handlers) == 1
    handler = rotating_handlers[0]
    assert handler.maxBytes == 1024
    assert handler.backupCount == 3


def test_setup_logging_file_override(tmp_path):
    """Test that log_file parameter overrides config."""
    config_file = tmp_path / "config.log"
    override_file = tmp_path / "override.log"

    config = LoggingConfig(file=config_file, console=False)
    setup_logging(config, log_file=override_file)

    logger = logging.getLogger("test")
    logger.info("Test message")

    # Should use override file, not config file
    assert override_file.exists()
    assert not config_file.exists()


def test_setup_logging_clears_existing_handlers():
    """Test that existing handlers are removed."""
    # Add a dummy handler
    root_logger = logging.getLogger()
    dummy_handler = logging.StreamHandler()
    root_logger.addHandler(dummy_handler)

    initial_count = len(root_logger.handlers)
    assert dummy_handler in root_logger.handlers

    # Setup logging should clear it
    config = LoggingConfig(console=False)
    setup_logging(config)

    # Dummy handler should be gone
    assert dummy_handler not in root_logger.handlers


def test_get_logger():
    """Test get_logger function."""
    logger = get_logger("test.module")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "test.module"


def test_logging_formatting(tmp_path):
    """Test log message formatting."""
    log_file = tmp_path / "test.log"
    config = LoggingConfig(file=log_file, console=False, level="DEBUG")

    setup_logging(config)

    logger = get_logger("test.formatter")
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")

    log_content = log_file.read_text()

    # Check all messages are present
    assert "Debug message" in log_content
    assert "Info message" in log_content
    assert "Warning message" in log_content
    assert "Error message" in log_content

    # Check log levels are included
    assert "DEBUG" in log_content
    assert "INFO" in log_content
    assert "WARNING" in log_content
    assert "ERROR" in log_content

    # Check logger name is included
    assert "test.formatter" in log_content

    # Check timestamp format (basic check for date-time pattern)
    assert "-" in log_content  # Date separators
    assert ":" in log_content  # Time separators


def test_third_party_loggers_suppressed():
    """Test that third-party library loggers are set to WARNING."""
    config = LoggingConfig(level="DEBUG", console=False)
    setup_logging(config)

    # Check third-party loggers are set to WARNING
    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_setup_logging_with_none_config(tmp_path):
    """Test setup_logging with None config uses defaults."""
    # This will use get_config() internally
    setup_logging(config=None)

    root_logger = logging.getLogger()
    assert root_logger.level > 0  # Some level is set
    assert len(root_logger.handlers) > 0  # At least one handler
