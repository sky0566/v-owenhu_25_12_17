"""
Structured logging for observability.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from enum import Enum


class LogLevel(str, Enum):
    """Log level enumeration."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredLogger:
    """
    Structured JSON logger for observability.
    All logs include request_id, timestamp, and event type.
    """
    
    def __init__(self, service_name: str = "routing-engine", version: str = "2.0.0"):
        self.service_name = service_name
        self.version = version
        self.logger = logging.getLogger(service_name)
        
        # Configure handler if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def log(
        self,
        level: LogLevel,
        event: str,
        request_id: str,
        context: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> None:
        """
        Log a structured event.
        
        Args:
            level: Log level
            event: Event name (e.g., "computation_completed")
            request_id: Unique request identifier
            context: Additional context data
            error: Error message if applicable
            correlation_id: Parent correlation ID
        """
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.value,
            "event": event,
            "request_id": request_id,
            "service": self.service_name,
            "version": self.version,
        }
        
        if correlation_id:
            log_entry["correlation_id"] = correlation_id
        
        if context:
            log_entry["context"] = context
        
        if error:
            log_entry["error"] = error
        
        # Log as JSON
        log_message = json.dumps(log_entry)
        
        # Route to appropriate log level
        if level == LogLevel.DEBUG:
            self.logger.debug(log_message)
        elif level == LogLevel.INFO:
            self.logger.info(log_message)
        elif level == LogLevel.WARNING:
            self.logger.warning(log_message)
        elif level == LogLevel.ERROR:
            self.logger.error(log_message)
        elif level == LogLevel.CRITICAL:
            self.logger.critical(log_message)
    
    def info(self, event: str, request_id: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Log info level event."""
        self.log(LogLevel.INFO, event, request_id, context)
    
    def error(self, event: str, request_id: str, error: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Log error level event."""
        self.log(LogLevel.ERROR, event, request_id, context, error)
    
    def warning(self, event: str, request_id: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Log warning level event."""
        self.log(LogLevel.WARNING, event, request_id, context)


class RequestTimer:
    """Context manager for timing requests."""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        return False
    
    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000.0
