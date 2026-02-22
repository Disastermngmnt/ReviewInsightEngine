"""
Simple in-memory rate limiter.
"""
import time
from collections import defaultdict
from threading import Lock
from typing import Optional
from utils.exceptions import RateLimitError


# Thread-safe in-memory rate limiter using the Token Bucket (Sliding Window) algorithm.
# Integrates with: main.py middleware to protect API endpoints from abuse and brute-force.
class RateLimiter:
    """
    Token bucket rate limiter.
    """
    def __init__(self, max_requests: int, window_seconds: int = 60):
        """
        Args:
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Stores timestamps of requests per identifier (e.g., IP address).
        self._requests = defaultdict(list)
        # Re-entrant lock to ensure thread safety in multi-threaded environments (FastAPI/Uvicorn).
        self._lock = Lock()
    
    # Validates if a specific identifier is still within its allotted request quota.
    # Integrates with: utils/exceptions.py (RateLimitError) to notify the caller of rejection.
    def check_rate_limit(self, identifier: str) -> None:
        """
        Check if request is within rate limit.
        
        Args:
            identifier: Unique identifier (e.g., IP address, user ID)
        
        Raises:
            RateLimitError: If rate limit exceeded
        """
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            
            # 1. Cleanup: Remove older request timestamps that fall outside the current window.
            self._requests[identifier] = [
                req_time for req_time in self._requests[identifier]
                if req_time > cutoff
            ]
            
            # 2. Enforcement: Reject the request if the bucket for this identifier is full.
            if len(self._requests[identifier]) >= self.max_requests:
                oldest = self._requests[identifier][0]
                # Calculate how many seconds before the oldest request expires from the window.
                retry_after = int(oldest + self.window_seconds - now)
                raise RateLimitError(
                    f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    details={
                        "max_requests": self.max_requests,
                        "window_seconds": self.window_seconds,
                        "retry_after": retry_after
                    }
                )
            
            # 3. Acceptance: Log the current request timestamp.
            self._requests[identifier].append(now)
    
    def get_remaining(self, identifier: str) -> int:
        """Get remaining requests for identifier."""
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            
            self._requests[identifier] = [
                req_time for req_time in self._requests[identifier]
                if req_time > cutoff
            ]
            
            return max(0, self.max_requests - len(self._requests[identifier]))
