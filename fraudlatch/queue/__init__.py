"""Queue abstraction contracts."""

from fraudlatch.queue.ports import MessageHandle, QueueMessage, QueuePort
from fraudlatch.queue.redis import (
    RedisConfigurationError,
    RedisStreamsQueue,
    create_redis_client,
    get_redis_url,
)
from fraudlatch.queue.retry import (
    PermanentProcessingError,
    RedisRetryHandler,
    RetryDecision,
    RetryPolicy,
    TransientProcessingError,
    classify_processing_error,
)

__all__ = [
    "MessageHandle",
    "QueueMessage",
    "QueuePort",
    "RedisConfigurationError",
    "RedisStreamsQueue",
    "create_redis_client",
    "get_redis_url",
    "PermanentProcessingError",
    "RedisRetryHandler",
    "RetryDecision",
    "RetryPolicy",
    "TransientProcessingError",
    "classify_processing_error",
]
