"""Typed exceptions for Lyfta API failures.

Callers should catch these instead of raw httpx exceptions.
"""

class LyftaError(Exception):
    """Base class for all Lyfta client errors."""

class LyftaAuthError(LyftaError):
    """API key missing, invalid, or lacks permission. (401, 403)"""

class LyftaNotFoundError(LyftaError):
    """Requested resource does not exist. (404)"""

class LyftaRateLimitError(LyftaError):
    """Rate limit exceeded. (429)"""
    
    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds

class LyftaServerError(LyftaError):
    """Lyfta server is broken. (5xx)"""

class LyftaNetworkError(LyftaError):
    """Could not reach Lyfta at all (DNS, timeout, connection drop)."""

class LyftaResponseError(LyftaError):
    """Got a 2xx response but the body wasn't usable (bad JSON, etc.)."""