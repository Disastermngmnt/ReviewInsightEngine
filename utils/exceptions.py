"""
Custom exception hierarchy for the application.
"""


# The root exception class for the entire Review Insight Engine.
# Integrates with: All custom error classes below to provide a consistent error structure (message + details).
class ReviewInsightError(Exception):
    """Base exception for all application errors."""
    def __init__(self, message: str, details: dict = None):
        self.message = message
        # Optional dictionary for providing granular error context (e.g., line numbers, field names).
        self.details = details or {}
        super().__init__(self.message)


# Hierarchy of specific error types categorized by functional area.
# Integrates with: try/except blocks throughout the core engine and API layers to handle failures gracefully.

class ValidationError(ReviewInsightError):
    """Raised when input validation (file size, format, constraints) fails."""
    pass


class AuthenticationError(ReviewInsightError):
    """Raised when an order ID is missing, malformed, or unauthorized."""
    pass


class FileProcessingError(ReviewInsightError):
    """Raised when pandas fails to parse a CSV or Excel upload."""
    pass


class AnalysisError(ReviewInsightError):
    """Raised when the deterministic scoring or categorization logic hits a fault."""
    pass


class AIEngineError(ReviewInsightError):
    """Raised when the Google Gemini API returns malformed JSON or an error response."""
    pass


class DatabaseError(ReviewInsightError):
    """Raised when SQLAlchemy operations (query, commit) fail."""
    pass


class ConfigurationError(ReviewInsightError):
    """Raised when required environment variables (like API keys) are missing or invalid."""
    pass


class RateLimitError(ReviewInsightError):
    """Raised by the RateLimiter when a client exceeds their request quota."""
    pass
