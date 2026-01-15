"""
Structured logging configuration for Purple Agent.

Provides JSON-formatted logging with structured fields for observability.
Supports both pretty console output with colors and JSON file logging.
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class ColoredConsoleFormatter(logging.Formatter):
    """Console formatter with colors and pretty output for development."""
    
    # ANSI color codes
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Log level colors
    DEBUG = '\033[36m'      # Cyan
    INFO = '\033[32m'       # Green
    WARNING = '\033[33m'    # Yellow
    ERROR = '\033[91m'      # Bright Red
    CRITICAL = '\033[95m'   # Magenta
    
    LEVEL_COLORS = {
        logging.DEBUG: DEBUG,
        logging.INFO: INFO,
        logging.WARNING: WARNING,
        logging.ERROR: ERROR,
        logging.CRITICAL: CRITICAL,
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log with colors for console output."""
        level_color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        
        # Format timestamp
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        
        # Build formatted output
        message = record.getMessage()
        if record.levelno >= logging.ERROR:
            return f"{self.BOLD}{level_color}[{record.levelname}]{self.RESET} {timestamp} | {message}"
        else:
            return f"{level_color}[{record.levelname}]{self.RESET} {timestamp} | {message}"


class StructuredJSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    # ANSI color codes
    RED = '\033[91m'
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON with structured fields.
        Errors are displayed in red color.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON-formatted log string (with color for errors)
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields from record
        if hasattr(record, "tool_name"):
            log_data["tool_name"] = record.tool_name
        if hasattr(record, "task_id"):
            log_data["task_id"] = record.task_id
        
        # Add any extra dict passed to logger
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            for key, value in record.extra.items():
                if key not in log_data:
                    log_data[key] = value
        
        json_output = json.dumps(log_data)
        
        # Add red color for ERROR and CRITICAL logs
        if record.levelno >= logging.ERROR:
            return f"{self.RED}{json_output}{self.RESET}"
        
        return json_output


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure structured logging for Purple Agent.
    
    Supports two modes via LOG_FORMAT environment variable:
    - "pretty" (default): Colorful console output for development
    - "json": JSON structured output for production
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Check log format preference
    log_format = os.environ.get("LOG_FORMAT", "pretty").lower()
    
    if log_format == "json":
        # JSON output for production (structured logging)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(console_handler)
    else:
        # Pretty colored output for development
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredConsoleFormatter())
        logger.addHandler(console_handler)
    
    # Add file handler to logs/purple_agent.log (in purple-agent/logs/)
    try:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / "purple_agent.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(file_handler)
    except Exception as e:
        # Silently ignore file logging errors if they occur
        pass
    
    # Set library log levels
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
