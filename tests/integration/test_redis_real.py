import os

import pytest
from redis.asyncio import Redis

from fraudlatch.queue import RedisStreamsQueue
from tests.unit.test_redis_queue import event

pytestmark = pytest.mark.integration


@pytest.mark.anyio
async def test_real_redis_stream_round_trip() -> None:
    client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    queue = RedisStreamsQueue(
        client, stream="integration:transactions", group="integration-workers"
    )
    try:
        handle = await queue.publish(event())
        messages = await queue.consume(consumer="integration-1", count=1, block_ms=1000)
        assert messages[0].handle.message_id == handle.message_id
        await queue.ack(handle)
    finally:
        await client.delete(queue.stream_name)
        await client.aclose()
