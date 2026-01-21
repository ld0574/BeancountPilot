"""
Logging module
"""

import logging
import sys
from pathlib import Path
from typing import Optional


# Log directory
LOG_DIR = Path.home() / ".beancountpilot" / "logs"
LOG_FILE = LOG_DIR / "app.log"


def setup_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[Path] = None,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """
    Setup logger

    Args:
        name: Logger name
        level: Log level
        log_file: Log file path
        format_string: Log format string

    Returns:
        Configured logger
    """
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    logger.handlers.clear()

    # Default format
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    formatter = logging.Formatter(format_string)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_file is None:
        log_file = LOG_FILE

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get logger

    Args:
        name: Logger name

    Returns:
        Logger
    """
    # If already set up, return directly
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    # Otherwise set up new one
    return setup_logger(name)
