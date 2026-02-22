"""
Tests for rate limiter.
"""
import pytest
import time
from utils.rate_limiter import RateLimiter
from utils.exceptions import RateLimitError


class TestRateLimiter:
    def test_within_limit(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        
        for _ in range(5):
            limiter.check_rate_limit("user1")
        # Should not raise
    
    def test_exceeds_limit(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        
        for _ in range(3):
            limiter.check_rate_limit("user1")
        
        with pytest.raises(RateLimitError) as exc:
            limiter.check_rate_limit("user1")
        
        assert "Rate limit exceeded" in str(exc.value)
    
    def test_different_identifiers(self):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        
        limiter.check_rate_limit("user1")
        limiter.check_rate_limit("user1")
        limiter.check_rate_limit("user2")
        limiter.check_rate_limit("user2")
        # Should not raise - different users
    
    def test_window_expiration(self):
        limiter = RateLimiter(max_requests=2, window_seconds=1)
        
        limiter.check_rate_limit("user1")
        limiter.check_rate_limit("user1")
        
        # Wait for window to expire
        time.sleep(1.1)
        
        limiter.check_rate_limit("user1")
        # Should not raise - window expired
    
    def test_get_remaining(self):
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        
        assert limiter.get_remaining("user1") == 5
        
        limiter.check_rate_limit("user1")
        assert limiter.get_remaining("user1") == 4
        
        limiter.check_rate_limit("user1")
        assert limiter.get_remaining("user1") == 3
