"""
Input validation utilities.
"""
import re
from pathlib import Path
from typing import Any, Optional
from utils.exceptions import ValidationError


# Ensures the uploaded file has a supported extension (e.g., .csv, .xlsx).
# Integrates with: core/file_handler.py and config/environments.py (allowed list).
def validate_file_extension(filename: str, allowed_extensions: list[str]) -> None:
    """
    Validate file extension against allowed list.
    
    Args:
        filename: Name of the file
        allowed_extensions: List of allowed extensions (e.g., ['.csv', '.xlsx'])
    
    Raises:
        ValidationError: If extension is not allowed
    """
    if not filename:
        raise ValidationError("Filename cannot be empty")
    
    # Extract extension and compare against the whitelist.
    ext = Path(filename).suffix.lower()
    if ext not in [e.lower() for e in allowed_extensions]:
        raise ValidationError(
            f"File extension '{ext}' not allowed",
            details={"allowed": allowed_extensions, "received": ext}
        )


# Checks if the uploaded file's binary size is within defined safety limits.
# Integrates with: core/file_handler.py to prevent memory exhaustion or server overload.
def validate_file_size(size_bytes: int, max_size_mb: int) -> None:
    """
    Validate file size.
    
    Args:
        size_bytes: File size in bytes
        max_size_mb: Maximum allowed size in MB
    
    Raises:
        ValidationError: If file is too large
    """
    # Convert MB requirement to bytes for precise comparison.
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValidationError(
            f"File size ({size_bytes / 1024 / 1024:.2f}MB) exceeds maximum ({max_size_mb}MB)",
            details={"size_bytes": size_bytes, "max_bytes": max_bytes}
        )


# Normalizes and validates the format of user-provided Order IDs.
# Integrates with: core/auth.py to ensure sanitized strings are sent to the database.
def validate_order_id(order_id: str) -> str:
    """
    Validate and normalize order ID.
    
    Args:
        order_id: Raw order ID string
    
    Returns:
        Normalized order ID
    
    Raises:
        ValidationError: If order ID is invalid
    """
    if not order_id or not order_id.strip():
        raise ValidationError("Order ID cannot be empty")
    
    # Strip whitespace and force uppercase for database consistency.
    normalized = order_id.strip().upper()
    
    # Regex check: Alphanumeric characters, hyphens, and underscores only.
    if not re.match(r'^[A-Z0-9\-_]+$', normalized):
        raise ValidationError(
            "Order ID contains invalid characters",
            details={"order_id": order_id}
        )
    
    # Length constraints to prevent anomalous inputs.
    if len(normalized) < 3 or len(normalized) > 50:
        raise ValidationError(
            "Order ID must be between 3 and 50 characters",
            details={"length": len(normalized)}
        )
    
    return normalized


# Ensures the parsed dataframe meets the column and row requirements for analysis.
# Integrates with: core/file_handler.py to catch corrupt or incompatible binary parses.
def validate_dataframe_structure(columns: list[str], data: list[list]) -> None:
    """
    Validate basic dataframe structure.
    
    Args:
        columns: List of column names
        data: List of data rows
    
    Raises:
        ValidationError: If structure is invalid
    """
    if not columns:
        raise ValidationError("No columns found in data")
    
    if not data:
        raise ValidationError("No data rows found")
    
    # Detect duplicate headers which would break positional mapping.
    if len(columns) != len(set(columns)):
        duplicates = [col for col in columns if columns.count(col) > 1]
        raise ValidationError(
            "Duplicate column names found",
            details={"duplicates": list(set(duplicates))}
        )
    
    # Verify that data rows match the header count (spot check first 10 for performance).
    expected_cols = len(columns)
    for i, row in enumerate(data[:10]):  # Check first 10 rows
        if len(row) != expected_cols:
            raise ValidationError(
                f"Row {i} has {len(row)} columns, expected {expected_cols}",
                details={"row_index": i, "expected": expected_cols, "actual": len(row)}
            )


# Basic string sanitization to remove null bytes and handle length limits.
# Integrates with: Input ingestion points to provide a basic layer of text safety.
def sanitize_text_input(text: str, max_length: Optional[int] = None) -> str:
    """
    Sanitize text input by removing potentially harmful content.
    
    Args:
        text: Input text
        max_length: Optional maximum length
    
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Remove null bytes to prevent string truncation issues in some systems.
    sanitized = text.replace('\x00', '')
    
    # Truncate to the provided limit (if any) to prevent excessive memory/token usage.
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized.strip()
