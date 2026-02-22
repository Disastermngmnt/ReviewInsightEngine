"""
Centralized logging configuration.
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional


# Centrally configures a Python Logger with both console and optional file output.
# Integrates with: All modules via 'setup_logger(__name__)' for consistent trace auditing.
def setup_logger(
    name: str,
    level: str = "INFO",
    log_file: Optional[str] = None,
    # Max size before rotation (defaults to 10MB).
    max_bytes: int = 10485760,  
    # Number of archived log files to retain.
    backup_count: int = 5
) -> logging.Logger:
    """
    Configure and return a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for file logging
        max_bytes: Max size of log file before rotation
        backup_count: Number of backup files to keep
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Singleton-like behavior: avoid attaching multiple handlers if the logger already exists.
    if logger.handlers:
        return logger
    
    # Unified log format across the entire application.
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 1. Console Handler: Prints logs to the standard output (terminal).
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 2. File Handler (Optional): Writes logs to a rotating physical file.
    # Integrates with: The local filesystem to persist application history.
    if log_file:
        log_path = Path(log_file)
        # Ensure the directory for the log file actually exists.
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger
