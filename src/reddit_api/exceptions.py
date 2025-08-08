"""
Reddit API Exceptions

Custom exception classes for Reddit data collection and storage operations.
"""


class RedditAPIError(Exception):
    """Base exception for Reddit API related errors."""
    pass


class StorageError(Exception):
    """Exception raised when storage operations fail."""
    pass


class CollectionError(Exception):
    """Exception raised when data collection operations fail."""
    pass


class ConfigurationError(Exception):
    """Exception raised when configuration is invalid."""
    pass


class RateLimitError(RedditAPIError):
    """Exception raised when Reddit API rate limits are exceeded."""
    pass


class AuthenticationError(RedditAPIError):
    """Exception raised when Reddit API authentication fails."""
    pass