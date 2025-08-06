"""
Reddit API Client with Rate Limiting and Circuit Breaker

Provides a rate-limited, fault-tolerant wrapper around the PRAW Reddit client.
"""

import logging
import time
from collections import deque
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

import praw

from .models import RedditConfig

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker state enumeration"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RateLimitedRedditClient:
    """
    Reddit client with rate limiting, circuit breaker, and exponential backoff.
    
    Implements:
    - Rate limiting (600 requests per 10 minutes)
    - Circuit breaker pattern for fault tolerance
    - Exponential backoff for retries
    - Request timing and metrics tracking
    """
    
    def __init__(self, config: RedditConfig):
        """
        Initialize the rate-limited Reddit client.
        
        Args:
            config: Reddit configuration containing API credentials and limits
        """
        self.config = config
        self.circuit_state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.request_times = deque(maxlen=config.max_requests_per_window)
        self.requests_made = 0
        self.requests_failed = 0
        
        # Initialize Reddit client in read-only mode
        # This avoids invalid_grant errors by using client credentials only
        self.reddit = praw.Reddit(
            client_id=config.client_id,
            client_secret=config.client_secret,
            user_agent=config.user_agent
            # Note: Intentionally NOT including username/password for read-only access
        )
        
        logger.info("Reddit client initialized in read-only mode")
    
    def _check_rate_limit(self) -> bool:
        """
        Check if we're within rate limits.
        
        Returns:
            True if within limits, False if at limit
        """
        now = datetime.now()
        window_start = now - timedelta(minutes=self.config.window_duration_minutes)
        
        # Remove old requests outside the window
        while self.request_times and self.request_times[0] < window_start:
            self.request_times.popleft()
        
        # Check if we're at the limit
        return len(self.request_times) < self.config.max_requests_per_window
    
    def _check_circuit_breaker(self) -> bool:
        """
        Check circuit breaker state and manage state transitions.
        
        Returns:
            True if requests should proceed, False if circuit is open
        """
        if self.circuit_state == CircuitBreakerState.OPEN:
            # Check if we should try half-open
            if self.last_failure_time and \
               (datetime.now() - self.last_failure_time).total_seconds() > 60:
                self.circuit_state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker moving to HALF_OPEN")
                return True
            return False
        return True
    
    def _record_success(self):
        """Record successful API call and update metrics"""
        self.failure_count = 0
        if self.circuit_state == CircuitBreakerState.HALF_OPEN:
            self.circuit_state = CircuitBreakerState.CLOSED
            logger.info("Circuit breaker CLOSED after successful request")
        
        self.request_times.append(datetime.now())
        self.requests_made += 1
    
    def _record_failure(self, error: Exception):
        """
        Record failed API call and update circuit breaker state.
        
        Args:
            error: The exception that caused the failure
        """
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.requests_failed += 1
        
        logger.error(f"Request failed (attempt {self.failure_count}): {error}")
        
        if self.failure_count >= self.config.circuit_breaker_threshold:
            self.circuit_state = CircuitBreakerState.OPEN
            logger.error(f"Circuit breaker OPEN after {self.failure_count} failures")
    
    def _exponential_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            Delay in seconds
        """
        delay = min(self.config.base_delay * (2 ** attempt), self.config.max_delay)
        return delay

    def make_request(self, request_func: Callable, *args, **kwargs) -> Any:
        """
        Make a rate-limited request with circuit breaker and exponential backoff.
        
        Args:
            request_func: Function to execute for the API request
            *args: Positional arguments for the request function
            **kwargs: Keyword arguments for the request function
            
        Returns:
            Result of the request function
            
        Raises:
            Exception: If all retry attempts fail or circuit breaker is open
        """
        if not self._check_circuit_breaker():
            raise Exception("Circuit breaker is OPEN")
        
        for attempt in range(self.config.max_retries):
            try:
                # Wait for rate limit
                if not self._check_rate_limit():
                    logger.warning("Rate limit reached, waiting...")
                    time.sleep(1)  # Simple rate limiting
                
                # Make the request
                result = request_func(*args, **kwargs)
                self._record_success()
                return result
                
            except Exception as e:
                self._record_failure(e)
                
                if attempt < self.config.max_retries - 1:
                    delay = self._exponential_backoff(attempt)
                    logger.info(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    raise e
    
    def get_metrics(self) -> dict:
        """
        Get current API usage metrics.
        
        Returns:
            Dictionary containing current metrics
        """
        return {
            'requests_made': self.requests_made,
            'requests_failed': self.requests_failed,
            'circuit_state': self.circuit_state.value,
            'current_window_requests': len(self.request_times),
            'requests_remaining': self.config.max_requests_per_window - len(self.request_times),
            'failure_count': self.failure_count
        }